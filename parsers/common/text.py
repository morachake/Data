"""
parsers/common/text.py — low-level text cleaning used by all source parsers.

Rules
-----
- Strip Wikipedia/HTML footnote references: [1], [a], [nb 2], etc.
- Normalise various dash/hyphen characters to a plain hyphen (-) for scores.
- Collapse surrounding whitespace.
- Remove the narrow no-break space (U+202F) used sometimes in French sources.
"""

import re
import unicodedata

# Matches footnote refs like [1], [a], [nb 2], [note 1]
_FOOTNOTE = re.compile(r"\[[\w\s]*\d+\w*\]|\[\w+\]")

# Various dash characters → standard hyphen
_DASH_MAP = str.maketrans({
    "\u2013": "-",   # en dash
    "\u2014": "-",   # em dash
    "\u2212": "-",   # minus sign
    "\u2012": "-",   # figure dash
    "\ufe58": "-",   # small em dash
    "\u202f": " ",   # narrow no-break space → regular space
    "\u00a0": " ",   # non-breaking space
})


def strip_footnotes(text: str) -> str:
    """Remove bracketed footnote references."""
    return _FOOTNOTE.sub("", text)


def normalise_dashes(text: str) -> str:
    """Translate typographic dashes to plain hyphens."""
    return text.translate(_DASH_MAP)


def clean(text: str) -> str:
    """Full clean: strip footnotes → normalise dashes → collapse whitespace."""
    text = strip_footnotes(text)
    text = normalise_dashes(text)
    return " ".join(text.split())


def strip_accents(text: str) -> str:
    """Remove diacritical marks (ä→a, ñ→n, etc.)."""
    nfd = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
