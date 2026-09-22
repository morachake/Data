"""
entity_resolution/name_normalise.py

Produces canonical string forms used for blocking and scoring.
Depends on parsers/common/names.py for language-aware normalisation.
"""

from parsers.common.names import normalise, token_set


def canonical(name: str) -> str:
    """
    Return the canonical form of a player name.
    Suitable as a blocking key prefix (first 4 chars of sorted tokens).
    """
    return normalise(name)


def blocking_key(name: str) -> str:
    """
    A 4-char prefix of the canonical form used to restrict scoring pairs.
    All candidates with the same blocking_key are scored against each other.
    """
    canon = canonical(name)
    return canon[:4] if len(canon) >= 4 else canon


def token_overlap(name_a: str, name_b: str) -> float:
    """
    Jaccard similarity of token sets.
    Quick pre-filter before the full fuzzy score.
    """
    ta = token_set(name_a)
    tb = token_set(name_b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
