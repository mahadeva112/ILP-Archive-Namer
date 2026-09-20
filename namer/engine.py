"""Naming engine: builds and validates archive folder / file names.

Each of the eight naming categories in the spec is a Category object with
declarative field metadata (which the UI renders) and a build function
(which produces the name). Nothing about naming is decided outside this file.
"""
import re
from datetime import date as _date

from .registry import REGISTRY
from .slug import slugify, FORBIDDEN

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

LEGAL_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
# Windows MAX_PATH is 260; leave headroom for the NAS path plus inner filenames.
NAME_SOFT_LIMIT = 120


class SpecError(ValueError):
    pass


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def fmt_date(iso):
    """ISO yyyy-mm-dd -> dd-Mmm-yyyy (the only date format the spec allows)."""
    if not iso:
        raise SpecError("Date is required")
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", str(iso).strip())
    if not m:
        raise SpecError("Date must be yyyy-mm-dd, got " + repr(iso))
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        _date(y, mo, d)
    except ValueError as exc:
        raise SpecError("Not a real date: %s (%s)" % (iso, exc))
    return "%02d-%s-%d" % (d, MONTHS[mo - 1], y)


def fmt_month_year(iso):
    """ISO yyyy-mm (or yyyy-mm-dd) -> Mmm-yyyy."""
    if not iso:
        raise SpecError("Month is required")
    m = re.match(r"^(\d{4})-(\d{2})", str(iso).strip())
    if not m:
        raise SpecError("Month must be yyyy-mm, got " + repr(iso))
    y, mo = int(m.group(1)), int(m.group(2))
    if not 1 <= mo <= 12:
        raise SpecError("Month out of range: " + str(iso))
    return "%s-%d" % (MONTHS[mo - 1], y)


def norm_lang(code):
    code = (code or "").strip().lower()
    if not re.fullmatch(r"[a-z]{3}", code):
        raise SpecError(
            "Language code must be exactly 3 lowercase letters, got " + repr(code))
    return code


def lang_title(code):
    """Categories #4 and #7 write the language as 'Tel', not 'tel'."""
    c = norm_lang(code)
    return c[0].upper() + c[1:]


def norm_video_id(vid):
    vid = (vid or "").strip()
    if not vid:
        raise SpecError("Video ID is required")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", vid):
        raise SpecError(
            "Video ID may only contain letters, digits, hyphen and underscore "
            "(got " + repr(vid) + ")")
    return vid


def need_slug(title, force_title_case=False, label="Title"):
    slug = slugify(title, force_title_case)
    if not slug:
        raise SpecError(label + " is required (and must contain letters or digits)")
    return slug


# --------------------------------------------------------------------------
# name segments
#
# A builder returns the name in labelled pieces rather than as one string, and
# the string is the concatenation of those pieces. The UI can then say which
# field produced which part of the name -- a swapped field or a wrong language
# code is visible at a glance instead of being read character by character --
# without a second parser that could disagree with the builder.
# --------------------------------------------------------------------------

def _part(label, text, field=None):
    return {"kind": "part", "label": label, "text": str(text), "field": field}


def _sep(text="_"):
    return {"kind": "sep", "label": "", "text": text, "field": None}


def joined(segments):
    return "".join(s["text"] for s in segments)


# --------------------------------------------------------------------------
# category builders
# --------------------------------------------------------------------------

def _yt_style(f):
    """Shared shape for #1, #2, #6:  <PREFIX><lang>_<id>_<Title>_<date>"""
    lang = norm_lang(f.get("lang"))
    prefix = REGISTRY.prefix_for(f.get("channel"), f.get("platform"))
    if not prefix:
        raise SpecError("Channel code is required")
    vid = norm_video_id(f.get("video_id"))
    slug = need_slug(f.get("title"), f.get("force_title_case"))
    return [
        _part("channel + lang", prefix + lang, "channel"),
        _sep(),
        _part("video code", vid, "video_id"),
        _sep(),
        _part("title", slug, "title"),
        _sep(),
        _part("created", fmt_date(f.get("date")), "date"),
    ]


def _build_dubbed_yt(f):
    return _yt_style(f)


def _build_other_channel_yt(f):
    return _yt_style(f)


def _build_unlisted_yt(f):
    """#3: the unique video code is the date the video was made, dd-Mmm-yyyy."""
    lang = norm_lang(f.get("lang"))
    prefix = REGISTRY.prefix_for(f.get("channel") or "SGL", f.get("platform") or "YT")
    made = fmt_date(f.get("video_made_date"))
    slug = need_slug(f.get("title"), f.get("force_title_case"))
    return [
        _part("channel + lang", prefix + lang, "channel"),
        _sep(),
        _part("video made", made, "video_made_date"),
        _sep(),
        _part("title", slug, "title"),
        _sep(),
        _part("created", fmt_date(f.get("date")), "date"),
    ]


def _build_department(f):
    """#4:  <DEPT>_<Video-Title>_<Lng>_<dd-Mmm-yyyy>"""
    dept = (f.get("department") or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3,4}", dept):
        raise SpecError("Department code must be 3 uppercase letters (e.g. IPC, HYS)")
    slug = need_slug(f.get("title"), f.get("force_title_case"))
    return [
        _part("department", dept, "department"),
        _sep(),
        _part("title", slug, "title"),
        _sep(),
        _part("language", lang_title(f.get("lang")), "lang"),
        _sep(),
        _part("created", fmt_date(f.get("date")), "date"),
    ]


def _build_sg_exclusive(f):
    """#5:  SGEX<lang><NNNN>_<Series-Name-Ep-##-Title>   (no date in this pattern)"""
    lang = norm_lang(f.get("lang"))
    code = (f.get("exclusive_code") or "").strip()
    if not re.fullmatch(r"\d{1,4}", code):
        raise SpecError(
            "Exclusive video code must be 1-4 digits (it is zero-padded to 4)")
    code = code.zfill(4)
    series = need_slug(f.get("series"), f.get("force_title_case"), "Series name")
    title = need_slug(f.get("title"), f.get("force_title_case"), "Episode title")
    ep = (f.get("episode") or "").strip()
    if ep:
        if not re.fullmatch(r"\d{1,3}", ep):
            raise SpecError("Episode number must be digits")
        middle = "%s-Ep-%02d-%s" % (series, int(ep), title)
    else:
        middle = "%s-%s" % (series, title)
    return [
        _part("series + lang", "SGEX" + lang, "lang"),
        _part("exclusive code", code, "exclusive_code"),
        _sep(),
        _part("series / episode / title", middle, "series"),
    ]


def _build_instagram(f):
    f = dict(f)
    if not f.get("channel"):
        f["channel"] = "SGIG"
    f.setdefault("platform", "IG")
    return _yt_style(f)


def _build_satsang(f):
    """#7: three sibling forms for the monthly satsang bundle."""
    my = fmt_month_year(f.get("month"))
    lng = lang_title(f.get("lang"))
    kind = (f.get("satsang_kind") or "video").strip()
    title = need_slug(f.get("title"), f.get("force_title_case"))
    tail = [_sep(), _part("title", title, "title"),
            _sep(), _part("language", lng, "lang")]
    if kind == "video":
        return [_part("satsang month", "Satsang-%s-Video" % my, "month")] + tail
    if kind == "audio_quote":
        return [_part("satsang month",
                      "Satsang-%s-Audio-Quote" % my, "month")] + tail
    if kind == "audio_gm":
        strand = need_slug(f.get("gm_strand"), f.get("force_title_case"),
                           "Meditation name")
        return [_part("satsang month", "Satsang-%s-Audio" % my, "month"),
                _sep(), _part("guided meditation", "GM", "satsang_kind"),
                _sep(), _part("meditation", strand, "gm_strand")] + tail
    raise SpecError("Unknown satsang type " + repr(kind))


def _build_dept_backup(f):
    """Department backup:  Department-Backup-ILP-Sep-2021"""
    dept = (f.get("department") or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3,4}", dept):
        raise SpecError("Department code must be 3 uppercase letters (e.g. ILP)")
    return [
        _part("backup", "Department-Backup"),
        _sep("-"),
        _part("department", dept, "department"),
        _sep("-"),
        _part("month", fmt_month_year(f.get("month")), "month"),
    ]


# --------------------------------------------------------------------------
# category table
# --------------------------------------------------------------------------

F_LANG = {"key": "lang", "label": "Language", "type": "lang", "required": True}
F_TITLE = {"key": "title", "label": "Video title in English", "type": "text",
           "required": True}
F_DATE = {"key": "date", "label": "Date translated video was created",
          "type": "date", "required": True}
F_VID = {"key": "video_id", "label": "Video URL or ID", "type": "video_url",
         "required": True}


class Category:
    def __init__(self, cid, label, spec_ref, blurb, example, fields, build,
                 has_inner_files=True, channel_filter=None):
        self.id = cid
        self.label = label
        self.spec_ref = spec_ref
        self.blurb = blurb
        self.example = example
        self.fields = fields
        self.segments = build
        self.has_inner_files = has_inner_files
        self.channel_filter = channel_filter

    def build(self, fields):
        """The finished name. Always the concatenation of its segments, so the
        two can never drift apart."""
        return joined(self.segments(fields))

    def meta(self):
        return {
            "id": self.id,
            "label": self.label,
            "spec_ref": self.spec_ref,
            "blurb": self.blurb,
            "example": self.example,
            "fields": self.fields,
            "has_inner_files": self.has_inner_files,
            "channel_filter": self.channel_filter,
            "nas": REGISTRY.nas_route(self.id),
        }


CATEGORIES = [
    Category(
        "dubbed_yt",
        "Dubbed YouTube video (Sadhguru / Isha Foundation)", "#1",
        "Dubbed videos from the Sadhguru and Isha Foundation channels.",
        "SGYThin_xVbcVQApKig_A-Lesson-From-Guru-Nanak_09-Jul-2021",
        [{"key": "channel", "label": "Channel", "type": "channel",
          "required": True, "default": "SGYT"},
         F_LANG, F_VID, F_TITLE, F_DATE],
        _build_dubbed_yt, channel_filter=["YT"],
    ),
    Category(
        "other_channel_yt",
        "Other official Isha channel / self-created", "#2",
        "Isha USA, Inner Engineering, IshaFoundationVideo, Sounds of Isha, and "
        "self-created videos published on YouTube.",
        "IECYThin_xVbcVQApKig_Take-Charge-Of-Your-Life-With-Shambhavi-"
        "Mahamudra-Kriya_07-Apr-2019",
        [{"key": "channel", "label": "Channel", "type": "channel",
          "required": True, "default": "IEC"},
         F_LANG, F_VID, F_TITLE, F_DATE],
        _build_other_channel_yt,
    ),
    Category(
        "unlisted_yt",
        "YouTube video whose original is unlisted", "#3",
        "Same structure as #1, except the unique video code is the date the "
        "video was made, because an unlisted original has no shareable code.",
        "SGLYThin_12-Mar-2021_A-Lesson-From-Guru-Nanak_09-Jul-2021",
        [{"key": "channel", "label": "Channel", "type": "channel",
          "required": True, "default": "SGL"},
         F_LANG,
         {"key": "video_made_date",
          "label": "Date the video was made (used as the video code)",
          "type": "date", "required": True},
         F_TITLE, F_DATE],
        _build_unlisted_yt,
    ),
    Category(
        "department",
        "Other video requested by a department", "#4",
        "Videos requested by another department (IPC, HYS, Dhyanalinga...). "
        "Note the field order differs from #1 and the language code is capitalised.",
        "IPC_How-To-Meditate_Tel_03-Oct-2022",
        [{"key": "department", "label": "Requesting department",
          "type": "department", "required": True},
         {"key": "title", "label": "Meaningful video title (English)",
          "type": "text", "required": True},
         F_LANG,
         {"key": "date", "label": "Video created date", "type": "date",
          "required": True}],
        _build_department,
    ),
    Category(
        "sg_exclusive",
        "Sadhguru Exclusive video", "#5",
        "Sadhguru Exclusive series. Uses a 4-digit registered video code and "
        "carries no date.",
        "SGEXhin0040_Realized-Beings-Ep-04-The-Rascal-Saint",
        [F_LANG,
         {"key": "exclusive_code", "label": "4-digit exclusive video code",
          "type": "text", "required": True, "placeholder": "0040"},
         {"key": "series", "label": "Series name", "type": "text",
          "required": True, "placeholder": "Realized Beings"},
         {"key": "episode", "label": "Episode number", "type": "text",
          "required": False, "placeholder": "4"},
         {"key": "title", "label": "Episode title", "type": "text",
          "required": True, "placeholder": "The Rascal Saint"}],
        _build_sg_exclusive,
    ),
    Category(
        "instagram",
        "Instagram reel / post", "#6",
        "Instagram content. The MP4 must start with 'Output' - never "
        "'IG_Output', which Archives rejects.",
        "SGIGhin_CgTjVwqFBTQ_Keep-This-In-Mind-For-Your-Next-Meal_07-Apr-2019",
        [{"key": "channel", "label": "Instagram account", "type": "channel",
          "required": True, "default": "SGIG"},
         F_LANG,
         {"key": "video_id", "label": "Reel URL or code", "type": "video_url",
          "required": True},
         {"key": "title", "label": "Video description (from the caption)",
          "type": "text", "required": True},
         F_DATE],
        _build_instagram, channel_filter=["IG"],
    ),
    Category(
        "satsang",
        "Satsang video / audio", "#7",
        "The monthly satsang bundle: one video, one audio quote, one guided "
        "meditation.",
        "Satsang-Jun-2022-Audio_GM_Chitshakti_Meditation-Peace_Tel",
        [{"key": "satsang_kind", "label": "Item type", "type": "select",
          "required": True, "default": "video",
          "options": [{"value": "video", "label": "Video"},
                      {"value": "audio_quote", "label": "Audio quote"},
                      {"value": "audio_gm",
                       "label": "Audio - guided meditation"}]},
         {"key": "month", "label": "Satsang month", "type": "month",
          "required": True},
         {"key": "gm_strand",
          "label": "Meditation name (guided meditation only)",
          "type": "text", "required": False, "placeholder": "Chitshakti",
          "show_if": {"satsang_kind": "audio_gm"}},
         {"key": "title", "label": "Title", "type": "text", "required": True,
          "placeholder": "What Is Grace"},
         F_LANG],
        _build_satsang,
    ),
    Category(
        "dept_backup",
        "Department backup", "backup",
        "Translated books, articles and other departmental content archived "
        "as a backup.",
        "Department-Backup-ILP-Sep-2021",
        [{"key": "department", "label": "Department", "type": "department",
          "required": True, "default": "ILP"},
         {"key": "month", "label": "Backup month", "type": "month",
          "required": True}],
        _build_dept_backup, has_inner_files=False,
    ),
]

CATEGORY_BY_ID = dict((c.id, c) for c in CATEGORIES)


# --------------------------------------------------------------------------
# inner file names
# --------------------------------------------------------------------------

def inner_files(slug, lang, voices=2):
    """The files that live inside a video folder (spec sections 1.1 - 1.5)."""
    lang = norm_lang(lang)
    out = []
    for n in range(1, max(1, min(int(voices), 12)) + 1):
        out.append({
            "role": "Voice %d" % n,
            "name": "Voice%d_%s_%s.wav" % (n, slug, lang),
            "folder": "Audio Output", "mandatory": False,
            "note": "Synced, de-breathed, otherwise unprocessed. "
                    "Mono WAV 24 bit 48 kHz.",
        })
    out += [
        {"role": "Script", "name": "Script_%s_%s.docx" % (slug, lang),
         "folder": "SRT_Transcript", "mandatory": False,
         "note": "Bilingual docx with the final translation, or a translated "
                 "transcript."},
        {"role": "Subtitles", "name": "Subtitles_%s_%s.srt" % (slug, lang),
         "folder": "SRT_Transcript", "mandatory": False,
         "note": "Only if an SRT adjusted to your language exists."},
        {"role": "Output MP4", "name": "Output_%s_%s.mp4" % (slug, lang),
         "folder": "Video Output", "mandatory": True,
         "note": "The published video. MUST start with 'Output' or Archives "
                 "rejects it."},
        {"role": "Facebook MP4", "name": "FB-Output_%s_%s.mp4" % (slug, lang),
         "folder": "Video Output", "mandatory": False,
         "note": "Only if a vertical subtitled version went to Facebook."},
    ]
    return out


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

_MONTH_SET = set(MONTHS)


def _caps_exempt(token, opaque):
    """Tokens the capital-after-separator rule must not touch.

    Video IDs are case-sensitive strings owned by YouTube/Instagram and may
    legitimately begin lowercase (xVbcVQApKig); the 3-letter language code is
    required by the spec to be lowercase; dates are digits and month names.
    """
    if token in opaque:
        return True
    if re.fullmatch(r"[a-z]{3}", token):       # language code
        return True
    if re.fullmatch(r"\d+", token):            # day / year
        return True
    if token in _MONTH_SET:                    # Jul
        return True
    return False


def validate_name(name, category=None, opaque=(), check_caps=True):
    """Check a finished name against the spec's hard rules.

    `opaque` lists substrings (video IDs) that are copied verbatim from an
    external source and so are exempt from the capitalisation rule. Pass
    check_caps=False for a name whose structure could not be identified, where
    there is no way to tell a video ID from a mis-capitalised word.
    Returns a list of {level, message, rule}.
    """
    opaque = set(o for o in opaque if o)
    issues = []

    def add(level, message, rule):
        issues.append({"level": level, "message": message, "rule": rule})

    if not name:
        add("error", "Name is empty", "non-empty")
        return issues

    if " " in name:
        add("error", "Contains a space - spaces are not allowed anywhere",
            "no-spaces")

    bad = sorted(set(c for c in name if c in FORBIDDEN))
    if bad:
        add("error", "Contains forbidden character(s): " + " ".join(bad),
            "only-hyphen-underscore")

    others = sorted(set(c for c in name
                        if not re.match(r"[A-Za-z0-9_-]", c)
                        and c not in bad and c != " "))
    if others:
        add("error",
            "Contains character(s) outside A-Z a-z 0-9 - _ : " + " ".join(others),
            "only-hyphen-underscore")

    # Spec: "Every alphabet after hyphen and underscore should be capital."
    # Checked per token so that exempt tokens (video IDs, language code, dates)
    # do not raise false alarms.
    for token in (re.split(r"[_-]", name)[1:] if check_caps else []):
        if not token or _caps_exempt(token, opaque):
            continue
        if token[0].isalpha() and token[0].islower():
            add("warning",
                "\"%s\" starts with a lowercase letter - the spec says every "
                "alphabet after a hyphen or underscore should be capital"
                % token,
                "capital-after-separator")
            break

    if "--" in name or "__" in name or "_-" in name or "-_" in name:
        add("warning", "Doubled or mixed separators", "single-separator")

    if name[0] in "-_" or name[-1] in "-_":
        add("error", "Starts or ends with a separator", "no-edge-separator")

    if len(name) > NAME_SOFT_LIMIT:
        add("warning",
            "%d characters - long names risk breaking the Windows 260-character "
            "path limit once the NAS path and inner filenames are added"
            % len(name),
            "path-length")

    if category == "instagram" and re.search(r"\bIG_Output", name):
        add("error", "Never name the MP4 'IG_Output' - Archives will reject it",
            "output-prefix")

    return issues


def segment_flag(text, opaque=()):
    """The worst thing wrong with one piece of a name, or None.

    Same rules as validate_name, scoped to a single segment so the UI can put
    the mark on the offending piece instead of describing it in prose.
    """
    if not text:
        return None
    opaque = set(o for o in opaque if o)
    if " " in text:
        return "error"
    if any(c in FORBIDDEN for c in text):
        return "error"
    if any(not re.match(r"[A-Za-z0-9_-]", c) for c in text):
        return "error"
    for token in re.split(r"[_-]", text):
        if not token or _caps_exempt(token, opaque):
            continue
        if token[0].isalpha() and token[0].islower():
            return "warning"
    return None


def flag_segments(segments, opaque=()):
    return [dict(s, flag=segment_flag(s["text"], opaque))
            if s["kind"] == "part" else dict(s, flag=None)
            for s in segments]


def build(category_id, fields):
    """Full result: folder name, inner files, validation, NAS destination."""
    cat = CATEGORY_BY_ID.get(category_id)
    if not cat:
        raise SpecError("Unknown category " + repr(category_id))

    segments = cat.segments(fields)
    folder = joined(segments)
    # A video ID is copied verbatim from the platform and is case-sensitive,
    # so it is exempt from the capitalisation rule.
    opaque = (str(fields.get("video_id") or "").strip(),)
    result = {
        "category": cat.id,
        "category_label": cat.label,
        "spec_ref": cat.spec_ref,
        "folder": folder,
        "segments": flag_segments(segments, opaque),
        "issues": validate_name(folder, cat.id, opaque),
        "nas": REGISTRY.nas_route(cat.id),
        "template": REGISTRY.template["subfolders"] if cat.has_inner_files else [],
        "files": [],
    }

    if cat.has_inner_files:
        lang = norm_lang(fields.get("lang"))
        if cat.id == "sg_exclusive":
            # The whole Series-Ep-Title block is the slug for inner files.
            slug = folder.split("_", 1)[1]
        else:
            slug = need_slug(fields.get("title"), fields.get("force_title_case"))
        result["files"] = inner_files(slug, lang, fields.get("voices") or 2)
        for f in result["files"]:
            f["issues"] = validate_name(f["name"].rsplit(".", 1)[0],
                                        cat.id, opaque)

    result["ok"] = not [i for i in result["issues"] if i["level"] == "error"]
    return result


# --------------------------------------------------------------------------
# parsing an existing name (checking what is already on the NAS)
# --------------------------------------------------------------------------

_PARSERS = [
    ("sg_exclusive", re.compile(
        r"^SGEX(?P<lang>[a-z]{3})(?P<exclusive_code>\d{4})"
        r"_(?P<title>[A-Za-z0-9-]+)$")),
    ("satsang", re.compile(
        r"^Satsang-(?P<month>[A-Z][a-z]{2}-\d{4})"
        r"-(?P<kind>Video|Audio-Quote|Audio)(?P<rest>_.+)"
        r"_(?P<lang>[A-Z][a-z]{2})$")),
    ("dept_backup", re.compile(
        r"^Department-Backup-(?P<department>[A-Z]{3,4})"
        r"-(?P<month>[A-Z][a-z]{2}-\d{4})$")),
    ("department", re.compile(
        r"^(?P<department>[A-Z]{3,4})_(?P<title>[A-Za-z0-9-]+)"
        r"_(?P<lang>[A-Z][a-z]{2})_(?P<date>\d{2}-[A-Z][a-z]{2}-\d{4})$")),
    ("dubbed_yt", re.compile(
        r"^(?P<prefix>[A-Z]{2,6})(?P<lang>[a-z]{3})_(?P<video_id>[A-Za-z0-9_-]+)"
        r"_(?P<title>[A-Za-z0-9-]+)_(?P<date>\d{2}-[A-Z][a-z]{2}-\d{4})$")),
]


# The same shapes with the contents left loose. A name that breaks the rules
# does not match the strict parsers at all, which is exactly when a person
# most needs to be told which category it was meant to be and which piece is
# wrong -- so the slots are identified first, then judged.
_LOOSE_PARSERS = [
    ("sg_exclusive", re.compile(
        r"^SGEX(?P<lang>[A-Za-z]{3})(?P<exclusive_code>\d{1,4})"
        r"_(?P<title>.+)$")),
    ("satsang", re.compile(
        r"^Satsang-(?P<month>.+?)-(?P<kind>Video|Audio-Quote|Audio)"
        r"(?P<rest>_.+)_(?P<lang>[A-Za-z]{3})$")),
    ("dept_backup", re.compile(
        r"^Department-Backup-(?P<department>[A-Za-z]{3,4})-(?P<month>.+)$")),
    ("department", re.compile(
        r"^(?P<department>[A-Za-z]{3,4})_(?P<title>.+)"
        r"_(?P<lang>[A-Za-z]{3})_(?P<date>\d.*)$")),
    ("dubbed_yt", re.compile(
        r"^(?P<prefix>[A-Za-z]{2,6})(?P<lang>[a-z]{3})"
        r"_(?P<video_id>[A-Za-z0-9_-]+)_(?P<title>.+)_(?P<date>\d.*)$")),
]

_SEG_LABELS = {
    "prefix": "channel", "lang": "language", "video_id": "video code",
    "title": "title", "date": "created", "department": "department",
    "month": "month", "exclusive_code": "exclusive code", "kind": "type",
    "rest": "title", "series": "series",
}


def _segments_from_match(name, m):
    """Slice a name into its matched groups, keeping the text between them as
    separators. The breakdown is then exactly what the parser saw."""
    spans = sorted((m.span(g), g) for g in m.groupdict()
                   if m.group(g) is not None)
    segs = []
    at = 0
    for (start, end), group in spans:
        if start < at:                       # overlapping group: already shown
            continue
        if start > at:
            segs.append(_sep(name[at:start]))
        text = name[start:end]
        lead = re.match(r"^[_-]*", text).group(0)
        rest = text[len(lead):]
        trail = re.search(r"[_-]*$", rest).group(0)
        core = rest[:len(rest) - len(trail)] if trail else rest
        if lead:
            segs.append(_sep(lead))
        if core:
            segs.append(_part(_SEG_LABELS.get(group, group.replace("_", " ")),
                              core, group))
        if trail:
            segs.append(_sep(trail))
        at = end
    if at < len(name):
        segs.append(_sep(name[at:]))
    return segs


def _fallback_segments(name):
    """No pattern recognised: show the underscore-separated fields as they are,
    so a person can still see which field is the broken one."""
    segs = []
    for i, field in enumerate(name.split("_")):
        if i:
            segs.append(_sep())
        if field:
            segs.append(_part("field %d" % (i + 1), field))
    return segs


_RX_DATE = re.compile(r"^\d{2}-(?:%s)-\d{4}$" % "|".join(MONTHS))
_RX_MONTH = re.compile(r"^(?:%s)-\d{4}$" % "|".join(MONTHS))


def _format_check(group, text, category):
    """Structural rules a segment must satisfy, beyond the character rules.

    validate_name works on the whole string and so cannot tell a date from a
    title; once a name is in labelled slots, a date that reads 9-July-2021 can
    be named as the thing that is wrong.
    """
    if group == "date" or (group == "video_id" and category == "unlisted_yt"):
        if not _RX_DATE.match(text):
            return ("Date \"%s\" is not dd-Mmm-yyyy (e.g. 09-Jul-2021)" % text,
                    "date-format")
    elif group == "month":
        if not _RX_MONTH.match(text):
            return ("Month \"%s\" is not Mmm-yyyy (e.g. Sep-2021)" % text,
                    "month-format")
    elif group == "lang":
        if category in ("department", "satsang"):
            if not re.fullmatch(r"[A-Z][a-z]{2}", text):
                return ("Language \"%s\" must be 3 letters capitalised in this "
                        "category (e.g. Tel)" % text, "language-code")
        elif not re.fullmatch(r"[a-z]{3}", text):
            return ("Language \"%s\" must be exactly 3 lowercase letters" % text,
                    "language-code")
    elif group == "exclusive_code":
        if not re.fullmatch(r"\d{4}", text):
            return ("Exclusive code \"%s\" must be 4 digits" % text,
                    "exclusive-code")
    return None


def _apply_format_checks(segments, category, issues):
    """Mark the segments that are structurally wrong and report each one once."""
    out = []
    for s in segments:
        problem = (_format_check(s.get("field"), s["text"], category)
                   if s["kind"] == "part" else None)
        if problem:
            message, rule = problem
            if not any(i["rule"] == rule for i in issues):
                issues.append({"level": "error", "message": message, "rule": rule})
            s = dict(s, flag="error", note=message)
        out.append(s)
    return out


def _strict_match(name):
    """(category, match) for a name that obeys the patterns, else (None, None)."""
    for cid, rx in _PARSERS:
        m = rx.match(name)
        if m:
            return _refine_yt(cid, m.groupdict()), m
    return None, None


def _refine_yt(cid, fields):
    """#1, #3 and #6 share one shape; the contents tell them apart."""
    if cid != "dubbed_yt":
        return cid
    if re.fullmatch(r"\d{2}-[A-Z][a-z]{2}-\d{4}", fields.get("video_id") or ""):
        return "unlisted_yt"
    if (fields.get("prefix") or "").upper().endswith("IG"):
        return "instagram"
    return cid


def parse_name(name):
    """Best-effort reverse of build(). Used to check names that already exist.

    `matched` is a category the name really is; `reads_as` is the category it
    was evidently meant to be when it breaks the rules badly enough not to
    parse. The UI must not present the second as the first.
    """
    name = (name or "").strip().strip("/\\")

    cid, m = _strict_match(name)
    if m:
        d = m.groupdict()
        opaque = (d.get("video_id") or "",)
        issues = validate_name(name, cid, opaque)
        segs = flag_segments(_segments_from_match(name, m), opaque)
        return {"matched": cid, "reads_as": cid, "fields": d,
                "segments": _apply_format_checks(segs, cid, issues),
                "issues": issues}

    for cid, rx in _LOOSE_PARSERS:
        m = rx.match(name)
        if not m:
            continue
        d = m.groupdict()
        cid = _refine_yt(cid, d)
        opaque = (d.get("video_id") or "",)
        issues = validate_name(name, cid, opaque)
        segs = flag_segments(_segments_from_match(name, m), opaque)
        return {"matched": None, "reads_as": cid, "fields": d,
                "segments": _apply_format_checks(segs, cid, issues),
                "issues": issues,
                "suggestion": suggest_fix(name, cid, m)}

    # Structure unknown, so a lowercase token cannot be told apart from a
    # video ID - reporting the capitalisation rule here would be a guess.
    return {"matched": None, "reads_as": None, "fields": {},
            "segments": flag_segments(_fallback_segments(name)),
            "issues": validate_name(name, check_caps=False)}


# --------------------------------------------------------------------------
# suggesting a correction
# --------------------------------------------------------------------------

_MONTH_NUM = dict((m.lower(), i + 1) for i, m in enumerate(MONTHS))
_MONTH_NUM.update(dict(
    (m, i + 1) for i, m in enumerate(
        ["january", "february", "march", "april", "may", "june", "july",
         "august", "september", "october", "november", "december"])))


def _fix_date(token):
    """dd-Mmm-yyyy from what someone actually typed, or None when the reading
    would be a guess (03-10-2022 is either 3 Oct or 10 Mar)."""
    t = re.sub(r"[./\s]", "-", (token or "").strip())
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.fullmatch(r"(\d{1,2})-([A-Za-z]+)-(\d{4})", t)
        if not m:
            return None
        mo = _MONTH_NUM.get(m.group(2).lower())
        if not mo:
            return None
        d, y = int(m.group(1)), int(m.group(3))
    try:
        _date(y, mo, d)
    except ValueError:
        return None
    return "%02d-%s-%d" % (d, MONTHS[mo - 1], y)


def _fix_month(token):
    t = re.sub(r"[./\s]", "-", (token or "").strip())
    m = re.fullmatch(r"([A-Za-z]+)-(\d{4})", t)
    if m:
        mo = _MONTH_NUM.get(m.group(1).lower())
        return "%s-%s" % (MONTHS[mo - 1], m.group(2)) if mo else None
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", t)
    if m and 1 <= int(m.group(2)) <= 12:
        return "%s-%s" % (MONTHS[int(m.group(2)) - 1], m.group(1))
    return None


def suggest_fix(name, category, match):
    """A tidied version of a name that broke the rules, or None.

    Deliberately timid. Only pieces whose correct form is unambiguous are
    rewritten -- a title is re-slugged, a readable date is reformatted, a
    language code is cased the way its category requires. A video code is
    copied verbatim and is never touched, an ambiguous date is left alone, and
    nothing is offered unless the result passes validation outright.
    """
    segs = _segments_from_match(name, match)
    lang_upper = category in ("department", "satsang")
    out = []

    for s in segs:
        if s["kind"] != "part":
            out.append(s)
            continue
        group, text = s.get("field"), s["text"]
        new = text

        if group in ("title", "rest", "series"):
            # The satsang 'rest' slot carries its own underscore-joined
            # fields (GM_Strand_Title), each a slug in its own right.
            new = "_".join(slugify(p) for p in text.split("_"))
        elif group == "date":
            new = _fix_date(text) or text
        elif group == "month":
            new = _fix_month(text) or text
        elif group == "lang":
            new = text.capitalize() if lang_upper else text.lower()
        elif group in ("prefix", "department"):
            new = text.upper()
        elif group == "video_id" and category == "unlisted_yt":
            new = _fix_date(text) or text

        out.append(dict(s, text=new))

    fixed = joined(out)
    if fixed == name or not fixed:
        return None

    vid = match.groupdict().get("video_id") or ""
    if [i for i in validate_name(fixed, category, (vid,)) if i["level"] == "error"]:
        return None
    if _strict_match(fixed)[1] is None:
        return None          # it must be a name the strict parser accepts
    return fixed
