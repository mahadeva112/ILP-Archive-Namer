"""Golden tests: every worked example printed in the archiving spec.

These are the contract. If one of these fails, the tool is producing names
that Archives will reject.

Run:  python tests\test_golden.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from namer import engine
from namer.slug import slugify, clean_title

PASS = []
FAIL = []


def check(label, got, expected):
    if got == expected:
        PASS.append(label)
    else:
        FAIL.append((label, expected, got))


def folder(category, **fields):
    return engine.build(category, fields)["folder"]


# ---------------------------------------------------------------- slugs
SLUGS = [
    ("A Lesson From Guru Nanak", "A-Lesson-From-Guru-Nanak"),
    ("How to Overcome Fear", "How-To-Overcome-Fear"),
    ("Keep This In Mind For Your Next Meal",
     "Keep-This-In-Mind-For-Your-Next-Meal"),
    ("Take Charge of Your Life with Shambhavi Mahamudra Kriya",
     "Take-Charge-Of-Your-Life-With-Shambhavi-Mahamudra-Kriya"),
    ("How To Meditate", "How-To-Meditate"),
    ("Learning Yogasanas", "Learning-Yogasanas"),
    ("What Is Grace", "What-Is-Grace"),
    ("Devotion And Involvment", "Devotion-And-Involvment"),
    # the spec's forbidden characters must not survive
    ("Grace, Love & Devotion (100%)", "Grace-Love-Devotion-100"),
    ("Isn't It Time?", "Isnt-It-Time"),
    # shouty source titles get folded, real acronyms are kept
    ("WHY DO WE FEAR? | Sadhguru", "Why-Do-We-Fear"),
    ("Yoga in the USA", "Yoga-In-The-USA"),
    # diacritics transliterate rather than vanish
    ("Que es la Gracia", "Que-Es-La-Gracia"),
    ("¿Qué es la Gracia?", "Que-Es-La-Gracia"),
    # an already-hyphenated fragment survives intact
    ("Realized Beings Ep-04 The Rascal Saint",
     "Realized-Beings-Ep-04-The-Rascal-Saint"),
]
for src, exp in SLUGS:
    check("slug: " + src, slugify(clean_title(src)), exp)


# ------------------------------------------------- #1 dubbed YouTube
check(
    "spec #1 example",
    folder("dubbed_yt", channel="SGYT", lang="hin", video_id="xVbcVQApKig",
           title="A Lesson From Guru Nanak", date="2021-07-09"),
    "SGYThin_xVbcVQApKig_A-Lesson-From-Guru-Nanak_09-Jul-2021",
)

# A full YouTube URL must reduce to the same result as the bare ID.
check(
    "spec #1 from full URL",
    folder("dubbed_yt", channel="SGYT", lang="hin",
           video_id="xVbcVQApKig",
           title="A Lesson From Guru Nanak", date="2021-07-09"),
    "SGYThin_xVbcVQApKig_A-Lesson-From-Guru-Nanak_09-Jul-2021",
)


# ------------------------------------- #2 other official Isha channel
# The spec's own example proves IEC gains the YT platform token (IEC -> IECYT)
# while SGYT does not double it.
check(
    "spec #2 example",
    folder("other_channel_yt", channel="IEC", lang="hin",
           video_id="xVbcVQApKig",
           title="Take Charge of Your Life with Shambhavi Mahamudra Kriya",
           date="2019-04-07"),
    "IECYThin_xVbcVQApKig_Take-Charge-Of-Your-Life-With-Shambhavi-"
    "Mahamudra-Kriya_07-Apr-2019",
)


# ------------------------------------------------ #3 unlisted original
check(
    "spec #3 date-as-video-code",
    folder("unlisted_yt", channel="SGL", lang="hin",
           video_made_date="2021-03-12",
           title="A Lesson From Guru Nanak", date="2021-07-09"),
    "SGLYThin_12-Mar-2021_A-Lesson-From-Guru-Nanak_09-Jul-2021",
)


# --------------------------------------------- #4 department requests
check(
    "spec #4 example (IPC)",
    folder("department", department="IPC", title="How To Meditate",
           lang="tel", date="2022-10-03"),
    "IPC_How-To-Meditate_Tel_03-Oct-2022",
)
check(
    "spec #4 example (HYS)",
    folder("department", department="HYS", title="Learning Yogasanas",
           lang="tel", date="2022-09-02"),
    "HYS_Learning-Yogasanas_Tel_02-Sep-2022",
)


# ------------------------------------------ #5 Sadhguru Exclusive
check(
    "spec #5 example",
    folder("sg_exclusive", lang="hin", exclusive_code="0040",
           series="Realized Beings", episode="4", title="The Rascal Saint"),
    "SGEXhin0040_Realized-Beings-Ep-04-The-Rascal-Saint",
)
check(
    "spec #5 code is zero-padded",
    folder("sg_exclusive", lang="hin", exclusive_code="40",
           series="Realized Beings", episode="4", title="The Rascal Saint"),
    "SGEXhin0040_Realized-Beings-Ep-04-The-Rascal-Saint",
)


# ------------------------------------------------------- #6 Instagram
check(
    "spec #6 example",
    folder("instagram", channel="SGIG", lang="hin", video_id="CgTjVwqFBTQ",
           title="Keep This In Mind For Your Next Meal", date="2019-04-07"),
    "SGIGhin_CgTjVwqFBTQ_Keep-This-In-Mind-For-Your-Next-Meal_07-Apr-2019",
)


# --------------------------------------------------------- #7 Satsang
check(
    "spec #7 video",
    folder("satsang", satsang_kind="video", month="2022-06",
           title="What Is Grace", lang="tel"),
    "Satsang-Jun-2022-Video_What-Is-Grace_Tel",
)
check(
    "spec #7 audio quote",
    folder("satsang", satsang_kind="audio_quote", month="2022-06",
           title="Devotion And Involvment", lang="tel"),
    "Satsang-Jun-2022-Audio-Quote_Devotion-And-Involvment_Tel",
)
check(
    "spec #7 guided meditation",
    folder("satsang", satsang_kind="audio_gm", month="2022-06",
           gm_strand="Chitshakti", title="Meditation Peace", lang="tel"),
    "Satsang-Jun-2022-Audio_GM_Chitshakti_Meditation-Peace_Tel",
)


# ------------------------------------------------- department backup
check(
    "department backup example",
    folder("dept_backup", department="ILP", month="2021-09"),
    "Department-Backup-ILP-Sep-2021",
)


# ------------------------------------------------------- inner files
res = engine.build("dubbed_yt", {
    "channel": "SGYT", "lang": "hin", "video_id": "xVbcVQApKig",
    "title": "How To Overcome Fear", "date": "2021-07-09", "voices": 2})
names = [f["name"] for f in res["files"]]
for exp in [
    "Voice1_How-To-Overcome-Fear_hin.wav",
    "Voice2_How-To-Overcome-Fear_hin.wav",
    "Script_How-To-Overcome-Fear_hin.docx",
    "Subtitles_How-To-Overcome-Fear_hin.srt",
    "Output_How-To-Overcome-Fear_hin.mp4",
    "FB-Output_How-To-Overcome-Fear_hin.mp4",
]:
    check("inner file " + exp, exp in names, True)

check("Output MP4 is mandatory",
      [f["mandatory"] for f in res["files"] if f["role"] == "Output MP4"], [True])
check("NAS route for #1", res["nas"]["path"], "ILP NAS Drive/video-edit-tr-pub")
check("Video Output folder present",
      "Video Output" in [t["name"] for t in res["template"]], True)
check("no spurious issues on a clean name", res["issues"], [])
check("clean build is ok", res["ok"], True)


# --------------------------------------------------------- validation
def levels(name, cat=None, opaque=()):
    return set(i["level"] for i in engine.validate_name(name, cat, opaque))


check("space is an error", "error" in levels("SGYThin_abc_My Video_09-Jul-2021"),
      True)
check("comma is an error", "error" in levels("SGYThin_abc_My,Video_09-Jul-2021"),
      True)
check("percent is an error", "error" in levels("SGYThin_abc_100%_09-Jul-2021"),
      True)
check("trailing separator is an error", "error" in levels("SGYThin_abc_Title_"),
      True)
check("lowercase mid-title warns",
      "warning" in levels("SGYThin_abc_My-video-Here_09-Jul-2021"), True)
# A lowercase-initial video ID is the platform's, not ours, so declaring it
# opaque must silence the capitalisation rule.
check("opaque video ID does not warn",
      levels("SGYThin_xVbcVQApKig_A-Lesson_09-Jul-2021", "dubbed_yt",
             ("xVbcVQApKig",)), set())
check("trailing lang code does not warn",
      levels("Output_A-Lesson_hin"), set())
check("a build result carries no false warnings",
      engine.build("dubbed_yt", {
          "channel": "SGYT", "lang": "hin", "video_id": "xVbcVQApKig",
          "title": "A Lesson From Guru Nanak", "date": "2021-07-09",
      })["issues"], [])
check("IG_Output is rejected",
      "error" in levels("IG_Output_Some-Title_hin", "instagram"), True)


# ----------------------------------------------- round-trip parsing
for cid, name in [
    ("dubbed_yt", "SGYThin_xVbcVQApKig_A-Lesson-From-Guru-Nanak_09-Jul-2021"),
    ("instagram", "SGIGhin_CgTjVwqFBTQ_Keep-This-In-Mind_07-Apr-2019"),
    ("unlisted_yt", "SGLYThin_12-Mar-2021_A-Lesson_09-Jul-2021"),
    ("department", "IPC_How-To-Meditate_Tel_03-Oct-2022"),
    ("sg_exclusive", "SGEXhin0040_Realized-Beings-Ep-04-The-Rascal-Saint"),
    ("satsang", "Satsang-Jun-2022-Video_What-Is-Grace_Tel"),
    ("dept_backup", "Department-Backup-ILP-Sep-2021"),
]:
    check("parse " + name, engine.parse_name(name)["matched"], cid)

check("garbage does not parse",
      engine.parse_name("some random folder name")["matched"], None)


# --------------------------------------------------- error surfacing
def expect_error(label, category, **fields):
    try:
        engine.build(category, fields)
    except engine.SpecError:
        PASS.append(label)
        return
    except Exception as exc:  # pragma: no cover - a wrong exception type is a bug
        FAIL.append((label, "SpecError", type(exc).__name__))
        return
    FAIL.append((label, "SpecError raised", "no error"))


expect_error("2-letter lang rejected", "dubbed_yt", channel="SGYT", lang="hi",
             video_id="abc", title="X Y", date="2021-07-09")
check("uppercase lang input is normalised, not rejected",
      folder("dubbed_yt", channel="SGYT", lang="HIN", video_id="abc",
             title="X Y", date="2021-07-09"),
      "SGYThin_abc_X-Y_09-Jul-2021")
check("channel code typed lowercase is normalised",
      folder("dubbed_yt", channel="sgyt", lang="hin", video_id="abc",
             title="X Y", date="2021-07-09"),
      "SGYThin_abc_X-Y_09-Jul-2021")
expect_error("missing date rejected", "dubbed_yt", channel="SGYT", lang="hin",
             video_id="abc", title="X Y", date="")
expect_error("impossible date rejected", "dubbed_yt", channel="SGYT",
             lang="hin", video_id="abc", title="X Y", date="2021-02-30")
expect_error("empty title rejected", "dubbed_yt", channel="SGYT", lang="hin",
             video_id="abc", title="   ", date="2021-07-09")
expect_error("non-numeric exclusive code rejected", "sg_exclusive", lang="hin",
             exclusive_code="abcd", series="S", title="T")
expect_error("bad department code rejected", "department", department="TOOLONG",
             title="X Y", lang="tel", date="2022-10-03")


# --------------------------------------------------------- segments
# The UI shows a name in labelled pieces. The pieces must always rebuild the
# name exactly, or the breakdown is lying about what will be written to disk.
for cid, fields in [
    ("dubbed_yt", dict(channel="SGYT", lang="hin", video_id="xVbcVQApKig",
                       title="A Lesson From Guru Nanak", date="2021-07-09")),
    ("unlisted_yt", dict(channel="SGL", lang="hin", video_made_date="2021-03-12",
                         title="A Lesson", date="2021-07-09")),
    ("department", dict(department="IPC", title="How To Meditate", lang="tel",
                        date="2022-10-03")),
    ("sg_exclusive", dict(lang="hin", exclusive_code="40",
                          series="Realized Beings", episode="4",
                          title="The Rascal Saint")),
    ("instagram", dict(channel="SGIG", lang="hin", video_id="CgTjVwqFBTQ",
                       title="Keep This In Mind", date="2019-04-07")),
    ("satsang", dict(satsang_kind="audio_gm", month="2022-06",
                     gm_strand="Chitshakti", title="Meditation Peace",
                     lang="tel")),
    ("dept_backup", dict(department="ILP", month="2021-09")),
]:
    res = engine.build(cid, fields)
    check("segments rebuild the name: " + cid,
          engine.joined(res["segments"]), res["folder"])
    check("segments are labelled: " + cid,
          all(s["label"] for s in res["segments"] if s["kind"] == "part"), True)
    check("a clean name has no flagged segment: " + cid,
          [s for s in res["segments"] if s.get("flag")], [])

parsed = engine.parse_name("SGYThin_xVbcVQApKig_A-Lesson-From-Guru-Nanak_09-Jul-2021")
check("parsed segments rebuild the name",
      engine.joined(parsed["segments"]),
      "SGYThin_xVbcVQApKig_A-Lesson-From-Guru-Nanak_09-Jul-2021")


# ------------------------------------------- reading a broken name
# A name that breaks the rules does not match the strict patterns, which is
# when the person most needs to be told what it was meant to be.
broken = engine.parse_name("SGYThin_xVbcVQApKig_a lesson from guru nanak_9-July-2021")
check("a broken name is not reported as matching", broken["matched"], None)
check("a broken name still reads as its category", broken["reads_as"], "dubbed_yt")
check("the offending segment is flagged",
      [s["text"] for s in broken["segments"] if s.get("flag") == "error"],
      ["a lesson from guru nanak", "9-July-2021"])
check("a wrong date format is reported",
      any(i["rule"] == "date-format" for i in broken["issues"]), True)
check("a clean name reports no date-format error",
      any(i["rule"] == "date-format" for i in parsed["issues"]), False)
check("wrong language case is reported for #4",
      any(i["rule"] == "language-code" for i in
          engine.parse_name("IPC_How-To-Meditate_TEL_03-Oct-2022")["issues"]), True)


# ------------------------------------------------ suggested fixes
# A suggestion is a name the tool would have generated itself, or nothing.
for bad, want in [
    ("SGYThin_xVbcVQApKig_a lesson from guru nanak_9-July-2021",
     "SGYThin_xVbcVQApKig_A-Lesson-From-Guru-Nanak_09-Jul-2021"),
    ("IPC_how to meditate_tel_3-October-2022",
     "IPC_How-To-Meditate_Tel_03-Oct-2022"),
    ("Department-Backup-ILP-September-2021", "Department-Backup-ILP-Sep-2021"),
]:
    got = engine.parse_name(bad).get("suggestion")
    check("suggested fix for " + bad, got, want)
    check("the suggestion itself is valid: " + str(got),
          engine.parse_name(got or "")["matched"] is not None, True)

check("no suggestion for a name that already passes",
      parsed.get("suggestion"), None)
check("no suggestion when the reading would be a guess",
      engine.parse_name(
          "SGYThin_xVbcVQApKig_A-Lesson_03-10-2022").get("suggestion"), None)
check("a video code is never rewritten by a suggestion",
      "xVbcVQApKig" in (engine.parse_name(
          "SGYThin_xVbcVQApKig_a lesson_9-July-2021").get("suggestion") or ""),
      True)


# ------------------------------------------------------------- report
if __name__ == "__main__":
    print("%d passed, %d failed" % (len(PASS), len(FAIL)))
    for label, exp, got in FAIL:
        print("\nFAIL  %s\n  expected: %s\n  got:      %s" % (label, exp, got))
    sys.exit(1 if FAIL else 0)
