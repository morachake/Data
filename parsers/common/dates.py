"""
parsers/common/dates.py — multilingual date parsing.

Supports:
  Phase 1: English (RSA)
  Phase 3: Arabic month names (Egypt, Morocco, Sudan)
            French month names (Morocco, Algeria, Tunisia, Ivory Coast, Mali)
"""

import re
from datetime import date, datetime

# ---------------------------------------------------------------------------
# English
# ---------------------------------------------------------------------------
_EN_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    # abbreviations
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12,
}

# ---------------------------------------------------------------------------
# French
# ---------------------------------------------------------------------------
_FR_MONTHS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}

# ---------------------------------------------------------------------------
# Arabic (transliterated forms that appear in Wikipedia)
# ---------------------------------------------------------------------------
_AR_MONTHS = {
    "يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "إبريل": 4,
    "مايو": 5, "يونيو": 6, "يوليو": 7, "أغسطس": 8,
    "سبتمبر": 9, "أكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
}

_ALL_MONTHS: dict[str, int] = {**_EN_MONTHS, **_FR_MONTHS, **_AR_MONTHS}

# ISO date: 2024-08-15 or 15/08/2024 or 15-08-2024
_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_DMY = re.compile(r"(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})")
# "15 August 2024" or "August 15, 2024"
_NAMED = re.compile(
    r"(\d{1,2})\s+([A-Za-zÀ-ÿ\u0600-\u06FF]+)\s+(\d{4})"
    r"|([A-Za-zÀ-ÿ\u0600-\u06FF]+)\s+(\d{1,2})[,\s]+(\d{4})"
)


def parse_date(text: str) -> date | None:
    """
    Try to parse a date from text.  Returns a ``datetime.date`` or None.
    Does not raise; caller decides what to do with None.
    """
    text = text.strip()

    m = _ISO.search(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    m = _DMY.search(text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d)
        except ValueError:
            pass

    m = _NAMED.search(text)
    if m:
        if m.group(1):  # DD Month YYYY
            day, month_str, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        else:           # Month DD, YYYY
            month_str, day, year = m.group(4).lower(), int(m.group(5)), int(m.group(6))
        mo = _ALL_MONTHS.get(month_str)
        if mo:
            try:
                return date(year, mo, day)
            except ValueError:
                pass

    return None


def parse_year(text: str) -> int | None:
    """Extract a 4-digit year from text."""
    m = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    return int(m.group(1)) if m else None
