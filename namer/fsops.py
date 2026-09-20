"""Filesystem operations: scaffold a folder, ingest media into it.

Safety rules baked in, not left to the UI:
  - Every operation is planned first. plan_*() touches nothing.
  - Ingest COPIES by default. Moving requires an explicit confirm_move flag.
  - An existing destination file is never overwritten unless the caller asks
    for it by name (on_conflict="replace").
  - Nothing is ever deleted. Move is copy-then-remove-source, and the source
    is only removed after the copy is verified by size.
  - Destinations are refused if they are a drive root, empty, or a file.
"""
import json
import os
import re
import shutil
import time

from . import SPEC_REVISION, __version__
from .engine import inner_files, need_slug, norm_lang, validate_name

# Extensions we recognise, mapped to the spec role they most likely fill.
AUDIO_EXT = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".m4a", ".aac", ".ogg"}
DOC_EXT = {".docx", ".doc", ".rtf", ".txt", ".odt", ".pdf"}
SUB_EXT = {".srt", ".vtt", ".ass", ".ssa", ".sbv"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".m4v", ".avi", ".wmv", ".mpg", ".mpeg",
             ".webm", ".mxf"}

# Project/session files that belong in the project folders, not the outputs.
PROJECT_EXT = {".prproj", ".aep", ".veg", ".drp", ".fcpxml", ".ptx", ".sesx",
               ".als", ".rpp", ".aup3", ".logicx", ".cpr", ".npr"}
FONT_EXT = {".ttf", ".otf", ".ttc", ".woff", ".woff2"}

# The spec's required container per role. A mismatch is a warning, not a
# silent rename: renaming a .mov to .mp4 would produce a broken file.
EXPECTED_EXT = {
    "voice": ".wav",
    "script": ".docx",
    "subtitles": ".srt",
    "output": ".mp4",
    "fb_output": ".mp4",
}

FB_HINT = re.compile(r"(?:^|[\W_])(fb|facebook|vert|vertical|portrait|9x16|916|reel)"
                     r"(?:$|[\W_])", re.IGNORECASE)
VOICE_NUM = re.compile(r"(?:voice|voc|vo|v|track|trk|spk|speaker)[\s_-]*(\d{1,2})",
                       re.IGNORECASE)

IGNORED_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}


class FsError(Exception):
    pass


# --------------------------------------------------------------------------
# path safety
# --------------------------------------------------------------------------

def _abs(path):
    return os.path.abspath(os.path.expanduser(str(path or "").strip().strip('"')))


def check_folder_name(name):
    """A generated folder name must never contain a path separator."""
    if not name or not str(name).strip():
        raise FsError("Folder name is empty")
    if re.search(r"[\\/]", name) or name in (".", ".."):
        raise FsError("Folder name must not contain a path separator: " + name)
    return name.strip()


def check_dest_root(root):
    """The parent directory a new archive folder will be created in."""
    if not str(root or "").strip():
        raise FsError("Choose a destination folder first")
    path = _abs(root)
    if os.path.isfile(path):
        raise FsError("Destination is a file, not a folder: " + path)
    drive, tail = os.path.splitdrive(path)
    if tail in ("", os.sep, "/"):
        raise FsError(
            "Refusing to archive directly into the root of %s - pick a real "
            "folder such as the NAS video-edit-tr-pub directory." % (drive or path))
    if not os.path.isdir(path):
        raise FsError("Destination folder does not exist: " + path)
    if not os.access(path, os.W_OK):
        raise FsError("No permission to write to: " + path)
    return path


# --------------------------------------------------------------------------
# scaffold
# --------------------------------------------------------------------------

def plan_scaffold(dest_root, folder_name, template, mandatory_only=False):
    """Work out which directories would be created. Touches nothing."""
    root = check_dest_root(dest_root)
    folder = check_folder_name(folder_name)
    target = os.path.join(root, folder)

    subs = [t for t in (template or [])
            if not mandatory_only or t.get("mandatory")]

    steps = [{
        "path": target, "rel": folder, "mandatory": True,
        "exists": os.path.isdir(target), "note": "Main archive folder",
    }]
    for t in subs:
        p = os.path.join(target, t["name"])
        steps.append({
            "path": p, "rel": folder + "/" + t["name"],
            "mandatory": bool(t.get("mandatory")),
            "exists": os.path.isdir(p), "note": t.get("note") or "",
        })

    warnings = []
    if os.path.isdir(target):
        existing = [e for e in os.listdir(target)
                    if e.lower() not in IGNORED_NAMES]
        warnings.append(
            "%s already exists and holds %d item(s). Existing files are left "
            "untouched; only missing subfolders are added."
            % (folder, len(existing)))
    if any(" " in t["name"] for t in subs):
        warnings.append(
            "Some template subfolder names contain spaces (as shipped in "
            "ARCHIVING TEMPLATE). The naming rules forbid spaces for archive "
            "folders - confirm with Archives whether subfolders are exempt.")

    return {"target": target, "steps": steps, "warnings": warnings,
            "to_create": sum(1 for s in steps if not s["exists"])}


def apply_scaffold(dest_root, folder_name, template, mandatory_only=False):
    """Create the directories. Idempotent - existing ones are left alone."""
    plan = plan_scaffold(dest_root, folder_name, template, mandatory_only)
    created, skipped = [], []
    for step in plan["steps"]:
        if step["exists"]:
            skipped.append(step["rel"])
            continue
        try:
            os.makedirs(step["path"], exist_ok=True)
            created.append(step["rel"])
        except OSError as exc:
            raise FsError("Could not create %s (%s)" % (step["path"], exc))
    return {"target": plan["target"], "created": created, "skipped": skipped,
            "warnings": plan["warnings"]}


# --------------------------------------------------------------------------
# scanning a source folder
# --------------------------------------------------------------------------

def scan_source(source_dir, recursive=True, max_files=400):
    """List candidate media files in a folder the user points at."""
    root = _abs(source_dir)
    if not os.path.isdir(root):
        raise FsError("Source folder does not exist: " + root)

    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in sorted(filenames):
            if fn.lower() in IGNORED_NAMES or fn.startswith("~$"):
                continue
            full = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            out.append({
                "path": full,
                "name": fn,
                "rel": os.path.relpath(full, root).replace("\\", "/"),
                "ext": os.path.splitext(fn)[1].lower(),
                "size": size,
                "role": guess_role(fn),
            })
            if len(out) >= max_files:
                return {"root": root, "files": resolve_roles(out),
                        "truncated": True}
        if not recursive:
            break
    return {"root": root, "files": resolve_roles(out), "truncated": False}


def guess_role(filename):
    """Best guess at which spec role a source file fills. Always user-editable."""
    stem, ext = os.path.splitext(filename)
    ext = ext.lower()

    if ext in SUB_EXT:
        return "subtitles"
    if ext in DOC_EXT:
        return "script"
    if ext in PROJECT_EXT:
        return "project"
    if ext in FONT_EXT:
        return "font"
    if ext in AUDIO_EXT:
        m = VOICE_NUM.search(stem)
        return "voice%d" % int(m.group(1)) if m else "voice1"
    if ext in VIDEO_EXT:
        return "fb_output" if FB_HINT.search(stem) else "output"
    return "unassigned"


def resolve_roles(files):
    """Second pass over guesses, using the set as a whole.

    Two audio files that both guessed voice1 get numbered in order, and if a
    folder holds two videos and one looks like the Facebook cut, the other is
    the main output.

    A file carrying role_locked was assigned by the user and is never
    reassigned - apply_ingest re-plans before executing, and guessing over a
    deliberate choice would silently archive the wrong take.
    """
    files = [dict(f) for f in files]
    free = [f for f in files if not f.get("role_locked")]

    audio = [f for f in free if f["role"].startswith("voice")]
    explicit = [f for f in audio if VOICE_NUM.search(os.path.splitext(f["name"])[0])]
    if len(audio) > 1 and len(explicit) < len(audio):
        # Numbering is ambiguous, so fall back to a stable filename order.
        for i, f in enumerate(sorted(audio, key=lambda x: x["name"].lower()), 1):
            f["role"] = "voice%d" % i
            f["role_note"] = "numbered by filename order - check this"

    videos = [f for f in free if f["role"] in ("output", "fb_output")]
    if len(videos) == 1:
        videos[0]["role"] = "output"
    elif len(videos) == 2:
        fb = [f for f in videos if f["role"] == "fb_output"]
        if len(fb) == 1:
            for f in videos:
                if f is not fb[0]:
                    f["role"] = "output"
        elif not fb:
            # Neither hints at Facebook; the larger file is normally the
            # landscape master.
            for f in sorted(videos, key=lambda x: -x["size"])[1:]:
                f["role_note"] = ("two videos and no Facebook hint - confirm "
                                  "which is the published output")
    return files


# --------------------------------------------------------------------------
# ingest
# --------------------------------------------------------------------------

def _target_map(fields, voices):
    """role -> (target stem, subfolder, mandatory, note) from the engine."""
    lang = norm_lang(fields.get("lang"))
    slug = fields.get("_slug") or need_slug(fields.get("title"),
                                            fields.get("force_title_case"))
    spec = inner_files(slug, lang, voices)
    out = {}
    for f in spec:
        stem = os.path.splitext(f["name"])[0]
        role = f["role"].lower().replace(" ", "")
        if role.startswith("voice"):
            key = "voice%s" % re.sub(r"\D", "", role)
        elif role == "script":
            key = "script"
        elif role == "subtitles":
            key = "subtitles"
        elif role == "outputmp4":
            key = "output"
        elif role == "facebookmp4":
            key = "fb_output"
        else:
            key = role
        out[key] = {"stem": stem, "folder": f["folder"],
                    "mandatory": f["mandatory"], "note": f["note"]}

    # Roles that are not spec deliverables but still need a home.
    out["project"] = {"stem": None, "folder": "Video Project",
                      "mandatory": False,
                      "note": "Editor/DAW project file - filed as-is"}
    out["font"] = {"stem": None, "folder": "Fonts", "mandatory": False,
                   "note": "Font used in the edit - filed as-is"}
    return out


def plan_ingest(target_folder, fields, files, mode="copy", on_conflict="skip",
                voices=None):
    """Decide what each file would be renamed to and where it would land.

    Touches nothing. Returns actions plus warnings, so the UI can show a
    dry run before anything happens.
    """
    folder = _abs(target_folder)
    if not os.path.isdir(folder):
        raise FsError("Archive folder does not exist yet - scaffold it first: "
                      + folder)
    if mode not in ("copy", "move"):
        raise FsError("mode must be 'copy' or 'move'")
    if on_conflict not in ("skip", "replace", "keep-both"):
        raise FsError("on_conflict must be 'skip', 'replace' or 'keep-both'")

    files = resolve_roles(files or [])
    if voices is None:
        voices = max([int(re.sub(r"\D", "", f["role"]) or 1)
                      for f in files if f["role"].startswith("voice")] or [1])
    targets = _target_map(fields, max(voices, 1))

    actions, warnings = [], []
    claimed = {}

    for f in files:
        role = f.get("role") or "unassigned"
        src = _abs(f["path"])
        act = {"src": src, "name": f["name"], "role": role,
               "size": f.get("size") or 0, "note": f.get("role_note") or ""}

        if role in ("unassigned", "skip"):
            act.update(action="skip", reason="No role assigned", dst=None)
            actions.append(act)
            continue

        spec = targets.get(role)
        if not spec:
            act.update(action="skip", dst=None,
                       reason="Unknown role '%s'" % role)
            actions.append(act)
            continue

        src_ext = os.path.splitext(f["name"])[1].lower()
        if spec["stem"]:
            # Keep the real container; the spec's expected extension is only a
            # warning, because renaming a container does not convert it.
            dst_name = spec["stem"] + src_ext
            base_role = re.sub(r"\d+$", "", role)
            want = EXPECTED_EXT.get(base_role)
            if want and src_ext != want:
                act["warn"] = ("The spec expects %s for this role. The file is "
                               "filed under its real extension (%s) - convert "
                               "it before archiving." % (want, src_ext))
        else:
            dst_name = f["name"]          # project files and fonts keep their name

        dst = os.path.join(folder, spec["folder"], dst_name)
        rel = spec["folder"] + "/" + dst_name

        name_issues = validate_name(os.path.splitext(dst_name)[0])
        if [i for i in name_issues if i["level"] == "error"]:
            act.update(action="skip", dst=dst, rel=rel,
                       reason="Generated name breaks the spec: "
                              + name_issues[0]["message"])
            actions.append(act)
            continue

        if rel in claimed:
            act.update(action="skip", dst=dst, rel=rel,
                       reason="Another file already maps to this name (%s). "
                              "Give one of them a different role."
                              % claimed[rel])
            actions.append(act)
            warnings.append("Two files map to " + rel)
            continue
        claimed[rel] = f["name"]

        if os.path.abspath(src) == os.path.abspath(dst):
            act.update(action="skip", dst=dst, rel=rel,
                       reason="Already in place with the right name")
            actions.append(act)
            continue

        if os.path.exists(dst):
            if on_conflict == "skip":
                act.update(action="skip", dst=dst, rel=rel,
                           reason="A file with this name already exists - "
                                  "left untouched")
            elif on_conflict == "replace":
                act.update(action=mode, dst=dst, rel=rel, replaces=True,
                           reason="Existing file will be overwritten")
                warnings.append("Overwriting " + rel)
            else:
                dst = _unique(dst)
                rel = spec["folder"] + "/" + os.path.basename(dst)
                act.update(action=mode, dst=dst, rel=rel,
                           reason="Name taken, filed as "
                                  + os.path.basename(dst))
        else:
            act.update(action=mode, dst=dst, rel=rel, reason="")

        actions.append(act)

    present = set(a["role"] for a in actions if a["action"] in ("copy", "move"))
    present |= set(a["role"] for a in actions
                   if a["action"] == "skip" and "already exists" in a.get("reason", ""))
    for role, spec in targets.items():
        if spec["mandatory"] and role not in present:
            warnings.append(
                "Missing %s (%s) - Archives requires it."
                % (spec["stem"] or role, spec["note"]))

    if mode == "move":
        warnings.append(
            "Move mode removes each source file after the copy is verified. "
            "Copy mode is the safer default.")

    return {"target": folder, "mode": mode, "on_conflict": on_conflict,
            "actions": actions, "warnings": warnings,
            "will_transfer": sum(1 for a in actions
                                 if a["action"] in ("copy", "move")),
            "will_skip": sum(1 for a in actions if a["action"] == "skip")}


def _unique(path):
    stem, ext = os.path.splitext(path)
    for n in range(2, 999):
        cand = "%s-%d%s" % (stem, n, ext)
        if not os.path.exists(cand):
            return cand
    raise FsError("Could not find a free filename for " + path)


def apply_ingest(target_folder, fields, files, mode="copy", on_conflict="skip",
                 voices=None, confirm_move=False):
    """Execute a plan. Re-plans first so the UI cannot submit a stale one."""
    if mode == "move" and not confirm_move:
        raise FsError("Moving files needs confirm_move=True. Nothing was done.")

    plan = plan_ingest(target_folder, fields, files, mode, on_conflict, voices)
    results = []

    for act in plan["actions"]:
        if act["action"] == "skip":
            results.append(dict(act, status="skipped"))
            continue

        src, dst = act["src"], act["dst"]
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            # copy2 preserves timestamps, which matter for archive provenance.
            shutil.copy2(src, dst)

            src_size = os.path.getsize(src)
            dst_size = os.path.getsize(dst)
            if src_size != dst_size:
                raise FsError("Copy verification failed: %d bytes in, %d out"
                              % (src_size, dst_size))

            if act["action"] == "move":
                # Only now is it safe to let go of the original.
                os.remove(src)

            results.append(dict(act, status="moved" if act["action"] == "move"
                                else "copied"))
        except (OSError, shutil.Error, FsError) as exc:
            results.append(dict(act, status="failed", error=str(exc)))

    ok = [r for r in results if r["status"] in ("copied", "moved")]
    failed = [r for r in results if r["status"] == "failed"]

    return {"target": plan["target"], "mode": mode, "results": results,
            "warnings": plan["warnings"],
            "transferred": len(ok), "failed": len(failed),
            "skipped": sum(1 for r in results if r["status"] == "skipped"),
            "bytes": sum(r.get("size") or 0 for r in ok)}


# --------------------------------------------------------------------------
# manifest + history
# --------------------------------------------------------------------------

MANIFEST_NAME = "manifest.json"


def write_manifest(target_folder, category, fields, folder_name, ingest=None):
    """Record what this folder is and how it was built, inside the folder.

    Appends to an existing manifest's history rather than replacing it, so a
    second ingest does not erase the first.
    """
    folder = _abs(target_folder)
    if not os.path.isdir(folder):
        raise FsError("Archive folder does not exist: " + folder)

    path = os.path.join(folder, MANIFEST_NAME)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")

    doc = {"tool": "ILP Archive Namer", "tool_version": __version__,
           "spec_revision": SPEC_REVISION, "created": stamp, "events": []}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                existing = json.load(fh)
            if isinstance(existing, dict):
                doc["created"] = existing.get("created", stamp)
                doc["events"] = existing.get("events") or []
        except (ValueError, OSError):
            doc["events"] = []          # unreadable manifest: start a fresh log

    doc.update({
        "folder": folder_name,
        "category": category,
        "fields": {k: v for k, v in (fields or {}).items()
                   if not k.startswith("_")},
        "updated": stamp,
    })

    event = {"at": stamp, "tool_version": __version__}
    if ingest:
        event.update({
            "action": "ingest", "mode": ingest.get("mode"),
            "transferred": ingest.get("transferred"),
            "skipped": ingest.get("skipped"), "failed": ingest.get("failed"),
            "files": [{"from": r["name"], "to": r.get("rel"),
                       "status": r["status"]}
                      for r in ingest.get("results", [])],
        })
    else:
        event["action"] = "scaffold"
    doc["events"].append(event)

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)               # atomic, so a crash cannot truncate it
    return {"path": path, "events": len(doc["events"])}


def history_path():
    """A per-user log, kept out of the app folder so a read-only install works."""
    base = (os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
            or os.path.expanduser("~"))
    d = os.path.join(base, "ILP-Archive-Namer")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "history.jsonl")


def log_history(entry):
    """Append-only, one JSON object per line. Never rewritten."""
    try:
        with open(history_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(dict(entry,
                                     at=time.strftime("%Y-%m-%dT%H:%M:%S")),
                                ensure_ascii=False) + "\n")
    except OSError:
        pass                            # history is a convenience, never fatal


def clear_history():
    """Empty the log, keeping a timestamped copy next to it.

    The log is what `seen_before` uses to warn about re-archiving a name, so
    the old rows are renamed rather than deleted -- restoring is a rename back.
    """
    path = history_path()
    if not os.path.isfile(path):
        return {"ok": True, "cleared": 0, "backup": None, "path": path}
    total = 0
    try:
        with open(path, encoding="utf-8") as fh:
            total = sum(1 for line in fh if line.strip())
    except OSError:
        pass
    backup = os.path.join(os.path.dirname(path),
                          "history-cleared-%s.jsonl"
                          % time.strftime("%Y%m%d-%H%M%S"))
    try:
        os.replace(path, backup)
    except OSError as exc:
        return {"ok": False, "error": "Could not clear the history: %s" % exc,
                "path": path}
    return {"ok": True, "cleared": total, "backup": backup, "path": path}


def read_history(limit=60):
    """Most recent first, plus a duplicate-name index for reuse warnings."""
    path = history_path()
    if not os.path.isfile(path):
        return {"entries": [], "path": path}
    rows = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return {"entries": [], "path": path}
    return {"entries": list(reversed(rows))[:limit], "path": path,
            "total": len(rows)}


def seen_before(folder_name):
    """Has this exact folder name been archived from this machine already?"""
    if not folder_name:
        return []
    return [e for e in read_history(limit=10000)["entries"]
            if e.get("folder") == folder_name]
