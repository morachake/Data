"""
parsers/common/names.py — player and team name normalisation.

Used by the entity resolution pipeline to create a canonical form for
blocking (pre-filter) and scoring (fuzzy match) steps.

Phase 1: English only (RSA).
Phase 3: Arabic and French tables added.
"""

import re
import unicodedata

from parsers.common.text import strip_accents

# ---------------------------------------------------------------------------
# Arabic name normalisation (Phase 3 — Egyptian / Moroccan leagues)
# ---------------------------------------------------------------------------
#
# Common transliteration variants that appear in different Wikipedia/RSSSF
# editions of the same name.  Maps any variant to a canonical form.

ARABIC_FIRST_TOKENS: dict[str, str] = {
    "mohammed": "muhammad",
    "mohamed":  "muhammad",
    "mouhamed": "muhammad",
    "mehmed":   "muhammad",
    "ahmad":    "ahmed",
    "achmed":   "ahmed",
}

ARABIC_PREFIXES: dict[str, str] = {
    "al-":  "al",
    "el-":  "al",
    "el":   "al",
    "abd-el": "abd al",
    "abdel":  "abd al",
    "abdo":   "abd",
    "abou":   "abu",
}

# ---------------------------------------------------------------------------
# French accent normalisation (Phase 3 — Moroccan / Ivorian leagues)
# ---------------------------------------------------------------------------
# strip_accents() from text.py handles most cases (é→e, etc.)


# ---------------------------------------------------------------------------
# Core normalisation
# ---------------------------------------------------------------------------

def normalise(name: str) -> str:
    """
    Produce a canonical form for matching:
      1. Lowercase
      2. Strip diacritics
      3. Apply Arabic/French variant substitutions
      4. Sort name tokens alphabetically (handles "Last, First" vs "First Last")
      5. Collapse whitespace and punctuation
    """
    name = name.lower()
    name = strip_accents(name)

    # Remove punctuation except spaces and hyphens-within-words
    name = re.sub(r"[',\.]", " ", name)

    # Apply Arabic prefix normalisations
    for variant, canonical in ARABIC_PREFIXES.items():
        # Match at word boundary
        name = re.sub(r"\b" + re.escape(variant) + r"\b", canonical, name)

    tokens = name.split()
    # Apply first-token Arabic name substitutions
    tokens = [ARABIC_FIRST_TOKENS.get(t, t) for t in tokens]

    # Sort tokens so "John Smith" and "Smith John" produce the same key.
    tokens_sorted = sorted(tokens)
    return " ".join(tokens_sorted)


def token_set(name: str) -> frozenset[str]:
    """Return the set of normalised tokens — used in blocking."""
    return frozenset(normalise(name).split())


# ---------------------------------------------------------------------------
# French surname prefix normalisation (Phase 3 — Morocco, Algeria, Ivory Coast)
# ---------------------------------------------------------------------------
FRENCH_PARTICLES: dict[str, str] = {
    "de la":  "",
    "du":     "",
    "de":     "",
    "le":     "",
    "la":     "",
    "l'":     "",
}


def normalise_fr(name: str) -> str:
    """
    Extend normalise() with French particle stripping for Maghreb names.
    E.g.  "Rachid Haouari" vs "Rachid El-Haouari" → both → "haouari rachid"
    """
    name = name.lower()
    for particle in sorted(FRENCH_PARTICLES, key=len, reverse=True):
        name = name.replace(particle, " ")
    return normalise(name)


# ---------------------------------------------------------------------------
# Arabic transliteration table (extended, Phase 3)
# ---------------------------------------------------------------------------
# Common Egyptian/Moroccan player-name token variants → canonical form.
# Add rows here as new sources introduce new variants; keep sorted.
ARABIC_TOKENS_EXTENDED: dict[str, str] = {
    # Names
    "aboubaker": "abu bakr",
    "aboubakar": "abu bakr",
    "ibrahim":   "ibrahim",
    "ebrahim":   "ibrahim",
    "karim":     "karim",
    "kareem":    "karim",
    "mustafa":   "mustafa",
    "mostafa":   "mustafa",
    "mostapha":  "mustafa",
    "omar":      "umar",
    "omaer":     "umar",
    "walid":     "walid",
    "waleed":    "walid",
    "youssef":   "yusuf",
    "yusef":     "yusuf",
    "joseph":    "yusuf",   # rare but appears in historical RSSSF records
    "hassan":    "hasan",
    "hassen":    "hasan",
    "hussain":   "husayn",
    "hussein":   "husayn",
    "hossam":    "husam",
    "hosam":     "husam",
    "tarek":     "tariq",
    "taric":     "tariq",
    # Connectors
    "ben":       "ibn",
    "bel":       "ibn",
    "ould":      "ibn",     # Maghreb Amazigh connector
}


def normalise_ar(name: str) -> str:
    """
    Extend normalise() with Arabic transliteration correction for
    Egyptian and Moroccan player names.
    """
    name = normalise(name)  # base normalisation (lowercase, strip accents, sort tokens)
    tokens = name.split()
    tokens = [ARABIC_TOKENS_EXTENDED.get(t, t) for t in tokens]
    return " ".join(sorted(tokens))
