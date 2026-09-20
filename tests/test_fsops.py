"""Filesystem tests for scaffold + ingest.

Everything runs inside a throwaway temp tree. The destructive paths (move,
overwrite, conflict) are exercised deliberately, because those are the ones
that would cost someone their masters if they were wrong.

Run:  python tests\test_fsops.py
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from namer import fsops
from namer.registry import REGISTRY

PASS, FAIL = [], []
TEMPLATE = REGISTRY.template["subfolders"]

FIELDS = {"lang": "hin", "title": "How To Overcome Fear"}
FOLDER = "SGYThin_xVbcVQApKig_How-To-Overcome-Fear_09-Jul-2021"


def check(label, got, expected):
    if got == expected:
        PASS.append(label)
    else:
        FAIL.append((label, expected, got))


def truthy(label, got):
    check(label, bool(got), True)


def write(path, content=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(content)
    return path


def sandbox():
    return tempfile.mkdtemp(prefix="ilp-namer-test-")


# ======================================================== path safety
root = sandbox()
try:
    for label, fn in [
        ("empty destination refused", lambda: fsops.check_dest_root("")),
        ("missing destination refused",
         lambda: fsops.check_dest_root(os.path.join(root, "nope"))),
        ("drive root refused", lambda: fsops.check_dest_root("C:\\")),
        ("separator in folder name refused",
         lambda: fsops.check_folder_name("a/b")),
        ("dotdot folder name refused", lambda: fsops.check_folder_name("..")),
        ("empty folder name refused", lambda: fsops.check_folder_name("")),
    ]:
        try:
            fn()
            FAIL.append((label, "FsError", "no error"))
        except fsops.FsError:
            PASS.append(label)

    f = write(os.path.join(root, "a-file.txt"))
    try:
        fsops.check_dest_root(f)
        FAIL.append(("file as destination refused", "FsError", "no error"))
    except fsops.FsError:
        PASS.append("file as destination refused")

    check("valid destination accepted", fsops.check_dest_root(root),
          os.path.abspath(root))
finally:
    shutil.rmtree(root, ignore_errors=True)


# ========================================================== scaffold
root = sandbox()
try:
    plan = fsops.plan_scaffold(root, FOLDER, TEMPLATE)
    check("plan creates main + 7 subfolders", len(plan["steps"]), 8)
    check("plan writes nothing", os.path.isdir(os.path.join(root, FOLDER)), False)
    check("plan counts all as new", plan["to_create"], 8)
    truthy("plan warns about spaces in template names",
           any("spaces" in w for w in plan["warnings"]))

    res = fsops.apply_scaffold(root, FOLDER, TEMPLATE)
    target = os.path.join(root, FOLDER)
    check("main folder created", os.path.isdir(target), True)
    check("Video Output created",
          os.path.isdir(os.path.join(target, "Video Output")), True)
    check("all 8 reported created", len(res["created"]), 8)

    # Idempotent: running twice must not fail or duplicate.
    res2 = fsops.apply_scaffold(root, FOLDER, TEMPLATE)
    check("second run creates nothing", res2["created"], [])
    check("second run skips all 8", len(res2["skipped"]), 8)

    # Existing content must be reported and left alone.
    keeper = write(os.path.join(target, "Video Output", "keep-me.mp4"), b"safe")
    plan3 = fsops.plan_scaffold(root, FOLDER, TEMPLATE)
    truthy("existing folder is flagged",
           any("already exists" in w for w in plan3["warnings"]))
    fsops.apply_scaffold(root, FOLDER, TEMPLATE)
    check("existing file untouched by scaffold", os.path.isfile(keeper), True)

    # mandatory_only builds just the required folder.
    res4 = fsops.apply_scaffold(root, "OnlyMandatory", TEMPLATE,
                                mandatory_only=True)
    check("mandatory_only creates main + Video Output", len(res4["created"]), 2)
finally:
    shutil.rmtree(root, ignore_errors=True)


# ======================================================= role guessing
check("srt -> subtitles", fsops.guess_role("whatever.srt"), "subtitles")
check("docx -> script", fsops.guess_role("bilingual script.docx"), "script")
check("wav -> voice1", fsops.guess_role("dubbing.wav"), "voice1")
check("Voice2 detected", fsops.guess_role("Voice2_something.wav"), "voice2")
check("V3 detected", fsops.guess_role("V3-take.wav"), "voice3")
check("mp4 -> output", fsops.guess_role("final render.mp4"), "output")
check("fb mp4 -> fb_output", fsops.guess_role("final_FB_vertical.mp4"),
      "fb_output")
check("facebook word detected", fsops.guess_role("render-facebook.mov"),
      "fb_output")
check("premiere project detected", fsops.guess_role("edit.prproj"), "project")
check("font detected", fsops.guess_role("Mangal.ttf"), "font")
check("unknown -> unassigned", fsops.guess_role("notes.xyz"), "unassigned")

# Two unnumbered wavs must be numbered deterministically, not both voice1.
pair = fsops.resolve_roles([
    {"path": "b.wav", "name": "b-take.wav", "size": 10, "role": "voice1"},
    {"path": "a.wav", "name": "a-take.wav", "size": 20, "role": "voice1"},
])
check("ambiguous voices numbered by filename",
      sorted((f["name"], f["role"]) for f in pair),
      [("a-take.wav", "voice1"), ("b-take.wav", "voice2")])
truthy("ambiguous numbering is flagged",
       all(f.get("role_note") for f in pair))

# A single video is the main output even if the name hints Facebook.
one = fsops.resolve_roles([{"path": "v.mp4", "name": "reel.mp4", "size": 5,
                           "role": "fb_output"}])
check("lone video becomes output", one[0]["role"], "output")

# A role the user set by hand must survive re-planning, or apply_ingest would
# quietly archive the wrong take.
locked = fsops.resolve_roles([
    {"path": "b.wav", "name": "b-take.wav", "size": 10, "role": "voice2",
     "role_locked": True},
    {"path": "a.wav", "name": "a-take.wav", "size": 20, "role": "voice1",
     "role_locked": True},
])
check("locked roles are never renumbered",
      sorted((f["name"], f["role"]) for f in locked),
      [("a-take.wav", "voice1"), ("b-take.wav", "voice2")])

lone_locked = fsops.resolve_roles([{"path": "v.mp4", "name": "reel.mp4",
                                    "size": 5, "role": "fb_output",
                                    "role_locked": True}])
check("locked fb_output stays fb_output", lone_locked[0]["role"], "fb_output")


# =========================================================== ingest
root = sandbox()
try:
    src = os.path.join(root, "raw")
    fsops.apply_scaffold(root, FOLDER, TEMPLATE)
    target = os.path.join(root, FOLDER)

    write(os.path.join(src, "Voice1 take.wav"), b"a" * 100)
    write(os.path.join(src, "Voice2 take.wav"), b"b" * 120)
    write(os.path.join(src, "script bilingual.docx"), b"c" * 50)
    write(os.path.join(src, "subs.srt"), b"d" * 30)
    write(os.path.join(src, "final render.mp4"), b"e" * 900)
    write(os.path.join(src, "final FB vertical.mp4"), b"f" * 400)
    write(os.path.join(src, "notes.xyz"), b"g" * 10)
    write(os.path.join(src, ".DS_Store"), b"junk")

    scan = fsops.scan_source(src)
    names = [f["name"] for f in scan["files"]]
    check("scan finds 7 real files", len(scan["files"]), 7)
    check("scan ignores .DS_Store", ".DS_Store" in names, False)

    plan = fsops.plan_ingest(target, FIELDS, scan["files"])
    by_src = dict((a["name"], a) for a in plan["actions"])

    check("copy is the default mode", plan["mode"], "copy")
    check("voice1 renamed to spec", by_src["Voice1 take.wav"]["rel"],
          "Audio Output/Voice1_How-To-Overcome-Fear_hin.wav")
    check("voice2 renamed to spec", by_src["Voice2 take.wav"]["rel"],
          "Audio Output/Voice2_How-To-Overcome-Fear_hin.wav")
    check("script renamed to spec", by_src["script bilingual.docx"]["rel"],
          "SRT_Transcript/Script_How-To-Overcome-Fear_hin.docx")
    check("srt renamed to spec", by_src["subs.srt"]["rel"],
          "SRT_Transcript/Subtitles_How-To-Overcome-Fear_hin.srt")
    check("output renamed to spec", by_src["final render.mp4"]["rel"],
          "Video Output/Output_How-To-Overcome-Fear_hin.mp4")
    check("fb output renamed to spec", by_src["final FB vertical.mp4"]["rel"],
          "Video Output/FB-Output_How-To-Overcome-Fear_hin.mp4")
    check("unknown file is skipped", by_src["notes.xyz"]["action"], "skip")
    check("plan writes nothing",
          os.listdir(os.path.join(target, "Video Output")), [])

    res = fsops.apply_ingest(target, FIELDS, scan["files"])
    check("6 files transferred", res["transferred"], 6)
    check("nothing failed", res["failed"], 0)
    check("output landed", os.path.isfile(os.path.join(
        target, "Video Output", "Output_How-To-Overcome-Fear_hin.mp4")), True)
    check("copy left the source in place",
          os.path.isfile(os.path.join(src, "final render.mp4")), True)
    check("copied byte-for-byte", os.path.getsize(os.path.join(
        target, "Video Output", "Output_How-To-Overcome-Fear_hin.mp4")), 900)

    # Re-ingesting must not clobber what is already archived.
    res2 = fsops.apply_ingest(target, FIELDS, scan["files"])
    check("second ingest transfers nothing", res2["transferred"], 0)
    check("second ingest skips everything already there", res2["skipped"], 7)

    # keep-both files the newcomer alongside instead of overwriting.
    res3 = fsops.apply_ingest(target, FIELDS, scan["files"],
                              on_conflict="keep-both")
    landed = os.listdir(os.path.join(target, "Video Output"))
    truthy("keep-both adds a suffixed copy",
           any("-2." in n for n in landed))

    # replace overwrites only when explicitly asked.
    write(os.path.join(src, "final render.mp4"), b"z" * 1500)
    res4 = fsops.apply_ingest(target, FIELDS,
                              [f for f in scan["files"]
                               if f["name"] == "final render.mp4"],
                              on_conflict="replace")
    check("replace overwrites", os.path.getsize(os.path.join(
        target, "Video Output", "Output_How-To-Overcome-Fear_hin.mp4")), 1500)
    truthy("replace is warned about",
           any("Overwriting" in w for w in res4["warnings"]))
finally:
    shutil.rmtree(root, ignore_errors=True)


# ============================== user-assigned roles survive apply
root = sandbox()
try:
    src = os.path.join(root, "raw")
    fsops.apply_scaffold(root, FOLDER, TEMPLATE)
    target = os.path.join(root, FOLDER)
    write(os.path.join(src, "take-a.wav"), b"a" * 10)
    write(os.path.join(src, "take-b.wav"), b"b" * 20)

    files = fsops.scan_source(src)["files"]
    # Deliberately invert what the guesser chose, the way a user would.
    for f in files:
        f["role"] = "voice2" if f["name"] == "take-a.wav" else "voice1"
        f["role_locked"] = True

    res = fsops.apply_ingest(target, FIELDS, files)
    landed = dict((r["name"], r.get("rel")) for r in res["results"])
    check("hand-assigned voice2 survives apply", landed["take-a.wav"],
          "Audio Output/Voice2_How-To-Overcome-Fear_hin.wav")
    check("hand-assigned voice1 survives apply", landed["take-b.wav"],
          "Audio Output/Voice1_How-To-Overcome-Fear_hin.wav")
    check("the file the user called voice1 has voice1's bytes",
          os.path.getsize(os.path.join(
              target, "Audio Output",
              "Voice1_How-To-Overcome-Fear_hin.wav")), 20)
finally:
    shutil.rmtree(root, ignore_errors=True)


# ===================================================== move behaviour
root = sandbox()
try:
    src = os.path.join(root, "raw")
    fsops.apply_scaffold(root, FOLDER, TEMPLATE)
    target = os.path.join(root, FOLDER)
    mp4 = write(os.path.join(src, "render.mp4"), b"m" * 777)
    files = fsops.scan_source(src)["files"]

    # Move must refuse without the explicit confirmation flag.
    try:
        fsops.apply_ingest(target, FIELDS, files, mode="move")
        FAIL.append(("move refused without confirm_move", "FsError", "no error"))
    except fsops.FsError:
        PASS.append("move refused without confirm_move")
    check("refused move left the source alone", os.path.isfile(mp4), True)

    res = fsops.apply_ingest(target, FIELDS, files, mode="move",
                             confirm_move=True)
    check("move transferred the file", res["transferred"], 1)
    check("move removed the source", os.path.isfile(mp4), False)
    check("move preserved the bytes", os.path.getsize(os.path.join(
        target, "Video Output", "Output_How-To-Overcome-Fear_hin.mp4")), 777)
    truthy("move mode warns", any("Move mode" in w for w in res["warnings"]))
finally:
    shutil.rmtree(root, ignore_errors=True)


# ================================================ warnings and guards
root = sandbox()
try:
    src = os.path.join(root, "raw")
    fsops.apply_scaffold(root, FOLDER, TEMPLATE)
    target = os.path.join(root, FOLDER)

    # A .mov in the Output role keeps its real extension and warns.
    write(os.path.join(src, "master.mov"), b"v" * 10)
    plan = fsops.plan_ingest(target, FIELDS, fsops.scan_source(src)["files"])
    act = plan["actions"][0]
    check("mov keeps its own extension", act["rel"],
          "Video Output/Output_How-To-Overcome-Fear_hin.mov")
    truthy("container mismatch warns", "mp4" in act.get("warn", ""))

    # Missing mandatory Output is called out.
    shutil.rmtree(src)
    write(os.path.join(src, "only-subs.srt"), b"s")
    plan2 = fsops.plan_ingest(target, FIELDS, fsops.scan_source(src)["files"])
    truthy("missing Output is flagged",
           any("Output_" in w and "requires" in w for w in plan2["warnings"]))

    # Two files claiming one role: the second is skipped, never silently lost.
    shutil.rmtree(src)
    write(os.path.join(src, "a.srt"), b"1")
    write(os.path.join(src, "b.srt"), b"2")
    plan3 = fsops.plan_ingest(target, FIELDS, fsops.scan_source(src)["files"])
    skipped = [a for a in plan3["actions"] if a["action"] == "skip"]
    check("duplicate role skips exactly one", len(skipped), 1)
    truthy("duplicate role explains itself",
           "different role" in skipped[0]["reason"])

    # Ingest into a folder that was never scaffolded must fail loudly.
    try:
        fsops.plan_ingest(os.path.join(root, "ghost"), FIELDS, [])
        FAIL.append(("ingest without scaffold refused", "FsError", "no error"))
    except fsops.FsError:
        PASS.append("ingest without scaffold refused")
finally:
    shutil.rmtree(root, ignore_errors=True)


# =========================================================== manifest
root = sandbox()
try:
    fsops.apply_scaffold(root, FOLDER, TEMPLATE)
    target = os.path.join(root, FOLDER)

    fsops.write_manifest(target, "dubbed_yt", FIELDS, FOLDER)
    mpath = os.path.join(target, "manifest.json")
    check("manifest written", os.path.isfile(mpath), True)

    doc = json.load(open(mpath, encoding="utf-8"))
    check("manifest records the folder", doc["folder"], FOLDER)
    check("manifest records the category", doc["category"], "dubbed_yt")
    truthy("manifest records the spec revision", doc.get("spec_revision"))
    check("manifest has one event", len(doc["events"]), 1)

    src = os.path.join(root, "raw")
    write(os.path.join(src, "render.mp4"), b"m" * 12)
    ing = fsops.apply_ingest(target, FIELDS, fsops.scan_source(src)["files"])
    fsops.write_manifest(target, "dubbed_yt", FIELDS, FOLDER, ingest=ing)

    doc2 = json.load(open(mpath, encoding="utf-8"))
    check("manifest appends rather than replacing", len(doc2["events"]), 2)
    check("manifest keeps the original created stamp",
          doc2["created"], doc["created"])
    check("ingest event names the action", doc2["events"][1]["action"], "ingest")
    truthy("ingest event lists files", doc2["events"][1]["files"])

    # Private fields must not leak into the archive record.
    fsops.write_manifest(target, "dubbed_yt",
                         dict(FIELDS, _slug="X", _channel_touched=True), FOLDER)
    doc3 = json.load(open(mpath, encoding="utf-8"))
    check("underscore fields excluded",
          [k for k in doc3["fields"] if k.startswith("_")], [])

    # A corrupt manifest must not stop the tool.
    open(mpath, "w").write("{not json")
    fsops.write_manifest(target, "dubbed_yt", FIELDS, FOLDER)
    doc4 = json.load(open(mpath, encoding="utf-8"))
    check("corrupt manifest is rebuilt", doc4["folder"], FOLDER)
finally:
    shutil.rmtree(root, ignore_errors=True)


# ------------------------------------------------------------- report
if __name__ == "__main__":
    print("%d passed, %d failed" % (len(PASS), len(FAIL)))
    for label, exp, got in FAIL:
        print("\nFAIL  %s\n  expected: %r\n  got:      %r" % (label, exp, got))
    sys.exit(1 if FAIL else 0)
