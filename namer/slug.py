"""Title -> spec-compliant slug.

Spec rules encoded here:
  - each word starts uppercase
  - words joined with hyphens
  - only hyphens and underscores allowed as separators
  - no spaces, no special characters (, . % ' etc.)
  - "Every alphabet after hyphen and underscore should be capital"
"""
import re
import unicodedata

# Characters the spec calls out explicitly, plus the usual filesystem offenders.
FORBIDDEN = set(r""",.%'"()[]{}!?;:@#$^&*+=|\/<>~`""")

# Removed with no word break, so contractions stay one word.
ELIDED = set("'’ʼ`´")

# Latin transliterations that NFKD alone will not produce.
_SPECIAL_TRANSLIT = {
    "ß": "ss", "æ": "ae", "Æ": "Ae", "ø": "o", "Ø": "O",
    "œ": "oe", "Œ": "Oe", "đ": "d", "Đ": "D", "ł": "l", "Ł": "L",
    "þ": "th", "Þ": "Th", "ð": "d", "Ð": "D",
}

# Noise commonly trailing YouTube / Instagram titles.
_TRAILING_NOISE = re.compile(
    r"(\s*[|\-–—]\s*(sadhguru|sadguru|isha|isha foundation|shorts)\s*$)"
    r"|(\s*#\w+)"
    r"|(\s*\bsadhguru\b\s*$)",
    re.IGNORECASE,
)


def transliterate(text: str) -> str:
    """Reduce any script to ASCII letters/digits as far as possible."""
    out = []
    for ch in text:
        if ch in _SPECIAL_TRANSLIT:
            out.append(_SPECIAL_TRANSLIT[ch])
            continue
        decomposed = unicodedata.normalize("NFKD", ch)
        stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
        out.append(stripped)
    return "".join(out)


def clean_title(text: str) -> str:
    """Strip channel-branding noise from a fetched title. Cosmetic, never silent:
    the UI shows the result so a human can correct it."""
    prev = None
    cur = (text or "").strip()
    while cur != prev:
        prev = cur
        cur = _TRAILING_NOISE.sub("", cur).strip()
        cur = cur.strip("|-–—:· ").strip()
    return cur or (text or "").strip()


def _looks_shouty(text: str) -> bool:
    """True when the source is mostly CAPS, so inner caps carry no meaning."""
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 4:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) > 0.6


def _cap_word(word: str, shouty: bool) -> str:
    """Uppercase the first letter. Preserve a short all-caps acronym as-is
    (USA, IE, GM) unless the whole title was shouting, in which case inner
    caps are noise and get folded down."""
    if not word:
        return ""
    if not shouty and word.isupper() and len(word) <= 4:
        return word
    return word[0].upper() + word[1:].lower()


def slugify(title: str, force_title_case: bool = False) -> str:
    """Convert a free-text title into a spec-compliant hyphenated slug.

    Existing hyphens in the input are preserved as word separators, so an
    already-formed fragment like "Ep-04" survives intact.
    """
    text = transliterate(title or "")
    shouty = force_title_case or _looks_shouty(text)

    # Apostrophes are elided outright ("Isn't" -> Isnt); every other forbidden
    # character becomes a word break ("Grace,Love" -> Grace-Love).
    text = "".join(c for c in text if c not in ELIDED)
    text = "".join(" " if (c in FORBIDDEN or c.isspace() or c == "_") else c
                   for c in text)
    # Anything still not [A-Za-z0-9-] (other scripts that would not transliterate) goes.
    text = re.sub(r"[^A-Za-z0-9\-]", " ", text)

    parts = []
    for chunk in text.split():
        # A chunk may itself contain hyphens; capitalise after each one.
        pieces = [p for p in chunk.split("-") if p]
        if pieces:
            parts.extend(_cap_word(p, shouty) for p in pieces)

    slug = "-".join(parts)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug


def enforce_caps_after_separator(name: str) -> str:
    """Spec: every alphabet following a hyphen or underscore is capital.
    Applied to a finished name; leaves lowercase language codes alone because
    those are inserted after this step by the builders."""
    return re.sub(r"([_-])([a-z])", lambda m: m.group(1) + m.group(2).upper(), name)
