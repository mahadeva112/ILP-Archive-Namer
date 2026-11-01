"""Self-update from GitHub Releases.

Once per start the app asks GitHub which release is the latest. A newer one is
offered in the page. When the user accepts, the running .exe downloads that
release's ILP-Archive-Namer.exe next to itself, checks it, swaps the two files
and starts the new one on the same port, so the open browser tab carries on.

Only the frozen .exe replaces itself. Run from source, the page links to the
release instead.

Publishing an update is: raise __version__ in namer/__init__.py, build the
.exe, and attach it to a GitHub release tagged v<version> (release.bat).
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request

REPO = "mahadeva112/ILP-Archive-Namer"
ASSET = "ILP-Archive-Namer.exe"
LATEST_URL = "https://api.github.com/repos/%s/releases/latest" % REPO
HEADERS = {"User-Agent": "ILP-Archive-Namer", "Accept": "application/vnd.github+json"}

# One answer per run: GitHub allows 60 unauthenticated calls an hour per IP,
# and an office shares one IP.
_LATEST = {}
_PENDING = {}       # "exe": path to start once the server has stopped


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def version_tuple(text):
    """'v1.10.2' -> (1, 10, 2), so 1.10 sorts after 1.9."""
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:3]) or (0,)


def check(current, timeout=6):
    """What GitHub says is the latest release, and whether it is newer."""
    if "result" in _LATEST:
        return _LATEST["result"]
    req = urllib.request.Request(LATEST_URL, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            rel = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # offline, proxy, rate limit: just no offer
        return {"ok": False, "current": current, "error": str(exc)}

    latest = (rel.get("tag_name") or "").lstrip("vV")
    asset = next((a for a in rel.get("assets") or [] if a.get("name") == ASSET), None)
    result = {
        "ok": True,
        "current": current,
        "latest": latest,
        "newer": version_tuple(latest) > version_tuple(current),
        "name": rel.get("name") or "v" + latest,
        "notes": (rel.get("body") or "")[:4000],
        "page": rel.get("html_url") or "https://github.com/%s/releases" % REPO,
        "can_install": is_frozen() and asset is not None,
    }
    _LATEST["result"] = result
    _LATEST["asset"] = asset
    return result


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _download(asset, dest, timeout=60):
    """Stream the release file to dest and check it is the file GitHub lists."""
    req = urllib.request.Request(asset["browser_download_url"],
                                 headers={"User-Agent": HEADERS["User-Agent"]})
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as out:
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
            out.write(chunk)

    if asset.get("size") and size != asset["size"]:
        raise IOError("got %d bytes, expected %d" % (size, asset["size"]))
    want = (asset.get("digest") or "").lower()
    if want.startswith("sha256:") and want[7:] != digest.hexdigest():
        raise IOError("checksum does not match the release")
    with open(dest, "rb") as f:
        if f.read(2) != b"MZ":
            raise IOError("not a Windows program")


def install(stop_server):
    """Download the newer .exe and swap it in. The restart happens a moment
    later, once the reply has reached the page; main() starts the new copy
    after the server has stopped and freed the port."""
    result = _LATEST.get("result") or {}
    asset = _LATEST.get("asset")
    if not is_frozen():
        return {"ok": False, "error": "Only the .exe can update itself. "
                "Download the new version from GitHub instead."}
    if not (result.get("newer") and asset):
        return {"ok": False, "error": "There is no newer release to install."}

    exe = os.path.abspath(sys.executable)
    new, old = exe + ".new", exe + ".old"
    try:
        _download(asset, new)
    except Exception as exc:
        _remove(new)
        return {"ok": False, "error": "The download failed (%s). Try again later." % exc}

    try:
        _remove(old)
        # Windows will not overwrite a running .exe but does let it be renamed.
        os.replace(exe, old)
        os.replace(new, exe)
    except OSError as exc:
        if not os.path.exists(exe) and os.path.exists(old):
            os.replace(old, exe)
        _remove(new)
        return {"ok": False, "error": "The app could not replace itself in %s (%s). "
                "Download the new version from GitHub instead."
                % (os.path.dirname(exe), exc.strerror or exc)}

    _PENDING["exe"] = exe
    threading.Timer(0.6, stop_server).start()
    return {"ok": True, "version": result["latest"]}


def relaunch_if_pending(port):
    """Called by main() after the server has stopped: start the new .exe on
    the same port, without opening another browser tab."""
    exe = _PENDING.get("exe")
    if not exe:
        return
    env = dict(os.environ)
    # A PyInstaller .exe started from another would otherwise reuse the
    # parent's unpacked files, which are deleted when the parent exits.
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([exe, "--port", str(port), "--no-open"], env=env,
                     cwd=os.path.dirname(exe), creationflags=flags, close_fds=True)


def clean_up_old():
    """Delete the previous .exe left by an update. It stays locked until the
    old process has fully exited, so keep trying for a little while."""
    if not is_frozen():
        return
    old = os.path.abspath(sys.executable) + ".old"

    def run():
        for _ in range(20):
            if not os.path.exists(old):
                return
            _remove(old)
            time.sleep(1.5)

    threading.Thread(target=run, daemon=True).start()
