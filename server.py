"""ILP Archive Namer - local application server.

Standard library only, on purpose: the whole point is that a translator can
run one file (or one .exe) with nothing installed.

    python server.py             start and open the browser
    python server.py --port 880  pin the port
    python server.py --no-open   do not launch a browser
    pythonw server.py            start with no console window at all

When there is no console to press Ctrl+C in (pythonw, or the windowless
launcher), the server watches for the browser's heartbeat and exits by itself
once the last tab is gone -- otherwise it would linger as an invisible process.
"""
import argparse
import json
import mimetypes
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from namer import SPEC_REVISION, __version__, engine, fsops
from namer.registry import REGISTRY
from namer.slug import clean_title, slugify
import updater

# Only one native dialog may be open at a time.
_DIALOG_LOCK = threading.Lock()

# Heartbeat: the page pings while it is open; the watchdog quits when it stops.
PING_INTERVAL = 4.0                 # must match the web UI's timer
PING_GRACE = 20.0                   # survives a reload or a slow machine
_LAST_PING = [0.0]

# When frozen by PyInstaller the bundle is unpacked to sys._MEIPASS.
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(BASE_DIR, "web")

# Only these are ever served from disk, so a path trick cannot reach the NAS.
STATIC_WHITELIST = {"index.html", "app.js", "styles.css"}


def extract_video_id(raw):
    """Pull the platform video code out of a pasted URL.

    Returns (id, platform, channel_hint). Falls back to treating the input as
    an already-bare ID, which is what a translator often pastes.
    """
    import re
    raw = (raw or "").strip()
    if not raw:
        return "", "", ""

    yt = re.search(
        r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/|v/)"
        r"|youtu\.be/)([A-Za-z0-9_-]{11})", raw)
    if yt:
        return yt.group(1), "YT", "SGYT"

    ig = re.search(r"instagram\.com/(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)", raw)
    if ig:
        return ig.group(1), "IG", "SGIG"

    fb = re.search(r"facebook\.com/.+?/videos/(\d+)", raw)
    if fb:
        return fb.group(1), "FB", "SGFB"

    if re.fullmatch(r"[A-Za-z0-9_-]{5,40}", raw):
        return raw, "", ""

    return raw, "", ""


def fetch_youtube_title(video_id, timeout=6):
    """YouTube oEmbed needs no API key. Done server-side so a corporate proxy
    or CORS policy cannot silently break title fetching in the browser."""
    url = ("https://www.youtube.com/oembed?url="
           + urllib.parse.quote("https://www.youtube.com/watch?v=" + video_id,
                                safe="")
           + "&format=json")
    req = urllib.request.Request(url, headers={"User-Agent": "ILP-Archive-Namer"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return {"title": data.get("title", ""), "author": data.get("author_name", "")}


def pick_folder(initial=None, title="Choose a folder"):
    """Open the OS folder picker.

    Tk is created and destroyed inside the calling request thread, which is
    what ThreadingHTTPServer gives us. If Tk is unavailable for any reason the
    caller just types the path instead, so this never becomes fatal.
    """
    if not _DIALOG_LOCK.acquire(blocking=False):
        return {"error": "A folder dialog is already open."}
    try:
        import tkinter
        from tkinter import filedialog

        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            chosen = filedialog.askdirectory(
                parent=root, title=title,
                initialdir=(initial if initial and os.path.isdir(initial)
                            else os.path.expanduser("~")),
                mustexist=True)
        finally:
            root.destroy()

        if not chosen:
            return {"cancelled": True}
        return {"path": os.path.abspath(chosen)}
    except Exception as exc:
        return {"error": "Could not open the folder picker (%s). Type or paste "
                         "the path instead." % type(exc).__name__}
    finally:
        _DIALOG_LOCK.release()


# --------------------------------------------------------------------------
# settings (last-used destination, remembered per user)
# --------------------------------------------------------------------------

def settings_path():
    base = (os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
            or os.path.expanduser("~"))
    d = os.path.join(base, "ILP-Archive-Namer")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "settings.json")


def load_settings():
    try:
        with open(settings_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(patch):
    data = load_settings()
    data.update({k: v for k, v in (patch or {}).items()
                 if k in ("last_dest", "last_source", "mode", "on_conflict",
                          "write_manifest")})
    try:
        tmp = settings_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, settings_path())
    except OSError:
        pass
    return data


def _manifest_wanted(payload):
    """Off by default: the archive folder holds the material, not our logs.

    Every run is still recorded in history.jsonl under LOCALAPPDATA. Anyone
    who wants the per-folder manifest back sets "write_manifest": true in
    settings.json, or sends the flag with the request.
    """
    if "write_manifest" in (payload or {}):
        return bool(payload["write_manifest"])
    return bool(load_settings().get("write_manifest", False))


def bootstrap_payload():
    return {
        "version": __version__,
        "settings": load_settings(),
        "spec_revision": SPEC_REVISION,
        "categories": [c.meta() for c in engine.CATEGORIES],
        "channels": REGISTRY.channels,
        "departments": REGISTRY.departments,
        "languages": REGISTRY.languages,
        "template": REGISTRY.template,
        "nas": REGISTRY.nas,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "ILPArchiveNamer/" + __version__

    # -------------------------------------------------- plumbing
    def log_message(self, fmt, *args):
        if os.environ.get("ILP_NAMER_VERBOSE"):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError):
            pass

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    # -------------------------------------------------- routes
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if route in ("/", "/index.html"):
            return self._static("index.html")
        if route.lstrip("/") in STATIC_WHITELIST:
            return self._static(route.lstrip("/"))
        if route == "/api/bootstrap":
            return self._send(200, bootstrap_payload())
        if route == "/api/lookup":
            return self._lookup(query.get("url", [""])[0])
        if route == "/api/ping":
            _LAST_PING[0] = time.time()
            return self._send(200, {"ok": True})
        if route == "/api/health":
            return self._send(200, {"ok": True, "version": __version__})
        if route == "/api/history":
            return self._send(200, fsops.read_history())
        if route == "/api/update/check":
            return self._send(200, updater.check(__version__))
        return self._send(404, {"error": "Not found: " + route})

    def do_POST(self):
        route = urllib.parse.urlparse(self.path).path
        payload = self._read_json()

        if route == "/api/build":
            return self._build(payload)
        if route == "/api/parse":
            return self._parse(payload)
        if route == "/api/pick-folder":
            return self._send(200, pick_folder(
                payload.get("initial"),
                payload.get("title") or "Choose a folder"))
        if route == "/api/history/clear":
            return self._fs(fsops.clear_history)
        if route == "/api/settings":
            return self._send(200, save_settings(payload))
        if route == "/api/update/install":
            return self._send(200, updater.install(self.server.shutdown))
        if route == "/api/scaffold/plan":
            return self._fs(lambda: fsops.plan_scaffold(
                payload.get("dest_root"), payload.get("folder"),
                REGISTRY.template["subfolders"],
                bool(payload.get("mandatory_only"))))
        if route == "/api/scaffold/apply":
            return self._scaffold_apply(payload)
        if route == "/api/source/scan":
            return self._fs(lambda: fsops.scan_source(
                payload.get("dir"), recursive=payload.get("recursive", True)))
        if route == "/api/ingest/plan":
            return self._fs(lambda: fsops.plan_ingest(
                payload.get("target"), payload.get("fields") or {},
                payload.get("files") or [],
                payload.get("mode") or "copy",
                payload.get("on_conflict") or "skip"))
        if route == "/api/ingest/apply":
            return self._ingest_apply(payload)
        if route == "/api/seen":
            return self._send(200, {"seen": fsops.seen_before(
                payload.get("folder"))})
        if route == "/api/reveal":
            return self._reveal(payload.get("path"))
        if route == "/api/slug":
            title = payload.get("title") or ""
            return self._send(200, {
                "cleaned": clean_title(title),
                "slug": slugify(clean_title(title),
                                bool(payload.get("force_title_case"))),
            })
        return self._send(404, {"error": "Not found: " + route})

    # -------------------------------------------------- handlers
    def _static(self, name):
        if name not in STATIC_WHITELIST:
            return self._send(403, {"error": "Forbidden"})
        path = os.path.join(WEB_DIR, name)
        if not os.path.isfile(path):
            return self._send(404, "Missing " + name, "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as fh:
            body = fh.read()
        return self._send(200, body, ctype + "; charset=utf-8")

    def _build(self, payload):
        category = payload.get("category")
        fields = payload.get("fields") or {}
        try:
            return self._send(200, engine.build(category, fields))
        except engine.SpecError as exc:
            return self._send(200, {"error": str(exc), "ok": False})
        except Exception as exc:  # never 500 at the user
            return self._send(200, {"error": "Unexpected: %s" % exc, "ok": False})

    def _fs(self, fn):
        """Run a filesystem helper, turning its errors into plain messages.
        A filesystem refusal is a normal outcome here, not a server fault."""
        try:
            return self._send(200, fn())
        except fsops.FsError as exc:
            return self._send(200, {"error": str(exc)})
        except engine.SpecError as exc:
            return self._send(200, {"error": str(exc)})
        except PermissionError as exc:
            return self._send(200, {"error": "Permission denied: %s" % exc})
        except OSError as exc:
            return self._send(200, {"error": "%s: %s"
                                    % (type(exc).__name__, exc)})
        except Exception as exc:
            return self._send(200, {"error": "Unexpected: %s" % exc})

    def _scaffold_apply(self, payload):
        def run():
            res = fsops.apply_scaffold(
                payload.get("dest_root"), payload.get("folder"),
                REGISTRY.template["subfolders"],
                bool(payload.get("mandatory_only")))
            if _manifest_wanted(payload):
                res["manifest"] = fsops.write_manifest(
                    res["target"], payload.get("category"),
                    payload.get("fields") or {}, payload.get("folder"))
            fsops.log_history({"action": "scaffold",
                               "folder": payload.get("folder"),
                               "category": payload.get("category"),
                               "target": res["target"],
                               "created": len(res["created"])})
            save_settings({"last_dest": payload.get("dest_root")})
            return res
        return self._fs(run)

    def _ingest_apply(self, payload):
        def run():
            res = fsops.apply_ingest(
                payload.get("target"), payload.get("fields") or {},
                payload.get("files") or [],
                payload.get("mode") or "copy",
                payload.get("on_conflict") or "skip",
                confirm_move=bool(payload.get("confirm_move")))
            if _manifest_wanted(payload):
                res["manifest"] = fsops.write_manifest(
                    payload.get("target"), payload.get("category"),
                    payload.get("fields") or {}, payload.get("folder"),
                    ingest=res)
            fsops.log_history({"action": "ingest",
                               "folder": payload.get("folder"),
                               "category": payload.get("category"),
                               "target": res["target"], "mode": res["mode"],
                               "transferred": res["transferred"],
                               "failed": res["failed"],
                               "bytes": res["bytes"]})
            save_settings({"last_source": payload.get("source_dir"),
                           "mode": res["mode"],
                           "on_conflict": payload.get("on_conflict") or "skip"})
            return res
        return self._fs(run)

    def _reveal(self, path):
        """Open a folder in Explorer. Read-only: it shows, never changes."""
        target = os.path.abspath(str(path or ""))
        if not os.path.isdir(target):
            return self._send(200, {"error": "Not a folder: " + target})
        try:
            os.startfile(target)        # Windows only, which is the target OS
            return self._send(200, {"ok": True})
        except (AttributeError, OSError) as exc:
            return self._send(200, {"error": str(exc)})

    def _parse(self, payload):
        try:
            return self._send(200, engine.parse_name(payload.get("name")))
        except Exception as exc:
            return self._send(200, {"error": str(exc)})

    def _lookup(self, raw):
        """URL -> video id, platform, suggested channel, and (YouTube) title."""
        vid, platform, channel = extract_video_id(raw)
        out = {"video_id": vid, "platform": platform, "channel": channel,
               "title": "", "title_source": None, "note": ""}
        if not vid:
            out["note"] = "Nothing recognised in that input."
            return self._send(200, out)

        if platform == "YT":
            try:
                meta = fetch_youtube_title(vid)
                raw_title = meta.get("title") or ""
                out["title_raw"] = raw_title
                out["title"] = clean_title(raw_title)
                out["slug"] = slugify(out["title"])
                out["title_source"] = "youtube-oembed"
                out["author"] = meta.get("author") or ""
            except (urllib.error.URLError, urllib.error.HTTPError,
                    socket.timeout, TimeoutError, ValueError) as exc:
                out["note"] = ("Could not reach YouTube to fetch the title "
                               "(%s). Type the English title by hand."
                               % type(exc).__name__)
        elif platform == "IG":
            out["note"] = ("Instagram does not expose captions without login - "
                           "paste the first sentence of the caption as the "
                           "description.")
        elif not platform:
            out["note"] = "Treated as a bare video code."
        return self._send(200, out)


def free_port(preferred=8737):
    for port in [preferred] + list(range(preferred + 1, preferred + 25)):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket() as sock:      # let the OS choose
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def has_console():
    """True when there is a window to press Ctrl+C in.

    On Windows ask the OS directly: pythonw.exe and a --noconsole build are GUI
    subsystem programs, so no console is attached and GetConsoleWindow gives 0.
    Checking sys.__stdout__ is not enough -- a redirected or inherited handle
    looks like a console but has no window the user can type into.
    """
    if os.name == "nt":
        try:
            import ctypes
            buf = (ctypes.c_uint * 1)()
            # 0 = no console attached, i.e. pythonw.exe or a --noconsole build.
            # GetConsoleWindow is no good here: Windows Terminal hosts a
            # pseudoconsole that has no window, so it reports 0 either way.
            return ctypes.windll.kernel32.GetConsoleProcessList(buf, 1) > 0
        except Exception:
            pass
    stream = getattr(sys, "__stdout__", None)
    if stream is None:
        return False
    try:
        return stream.fileno() >= 0
    except (AttributeError, ValueError, OSError):
        return False


def watch_browser(httpd):
    """Shut down once the browser has stopped pinging, so no ghost process."""
    while True:
        time.sleep(PING_INTERVAL)
        last = _LAST_PING[0]
        if last and time.time() - last > PING_GRACE:
            threading.Thread(target=httpd.shutdown, daemon=True).start()
            return


def main():
    ap = argparse.ArgumentParser(description="ILP Archive Namer")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--auto-exit", dest="auto_exit", action="store_true",
                    default=None,
                    help="quit when the browser tab closes (default without a console)")
    ap.add_argument("--no-auto-exit", dest="auto_exit", action="store_false",
                    help="keep running even after the browser tab closes")
    args = ap.parse_args()

    auto_exit = (not has_console()) if args.auto_exit is None else args.auto_exit

    port = args.port or free_port()
    # Bound to loopback only: this is a personal tool, not a shared service.
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = "http://127.0.0.1:%d/" % port

    updater.clean_up_old()
    print("ILP Archive Namer %s  (spec %s)" % (__version__, SPEC_REVISION))
    print("Running at " + url)
    print("Press Ctrl+C to stop.")

    if not args.no_open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    if auto_exit:
        # Give the browser a moment to load before the clock starts ticking.
        _LAST_PING[0] = time.time() + 15.0
        threading.Thread(target=watch_browser, args=(httpd,), daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
    # After an update: start the new .exe now that the port is free.
    updater.relaunch_if_pending(port)


if __name__ == "__main__":
    main()
