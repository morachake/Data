"""
parsers/wikipedia_season.py

Parses RawPageItem blocks (block_type='table') scraped from Wikipedia season
pages and produces typed StagingRow dicts for each data type.

Entry point
-----------
    parse(raw_item) -> list[dict]

Each returned dict has a ``_row_type`` key that tells the loader which staging
table to write to:
  - "stg_match"     → staging.stg_match
  - "stg_standing"  → staging.stg_standing
  - "stg_squad"     → staging.stg_squad

Only the results-matrix table produces stg_match rows.  The league table
(standings) and squad/top-scorer tables produce their own row types.

Results matrix detection
------------------------
Wikipedia PSL season pages contain a square N×N table where each cell is a
score ("home–away").  The first column and first row list team names.  We detect
this with the same logic as the legacy parse_results_matrix.py loader.
"""

import re
from typing import Any

from parsers.common.text import clean

SCORE_RE = re.compile(r"^(\d+)\s*[–\-]\s*(\d+)$")
FOOTNOTE_RE = re.compile(r"\[.*?\]")


def _clean_cell(cell: str) -> str:
    return FOOTNOTE_RE.sub("", cell).strip()


def _score_count(rows: list) -> int:
    body = rows[1:]
    return sum(1 for row in body for cell in row[1:] if SCORE_RE.match(_clean_cell(cell)))


def _is_results_matrix(rows: list) -> bool:
    if len(rows) < 5:
        return False
    header, body = rows[0], rows[1:]
    n = len(body)
    # Require at least 6 teams — smaller tables are almost always something
    # else (hat-trick logs, top-scorer lists, etc.) where column count and
    # incidental score-like values can trigger false positives.
    if n < 6:
        return False
    if len(header) - 1 != n:
        return False
    scores = _score_count(rows)
    complete = n * (n - 1)
    return scores >= 0.6 * complete or scores >= n


def _is_league_table(rows: list) -> bool:
    """Detect a standings table: first row has headers like P, W, D, L, Pts."""
    if not rows:
        return False
    header_text = " ".join(rows[0]).lower()
    pts_indicators = {"pts", "points", "pt"}
    return any(ind in header_text.split() for ind in pts_indicators)


def _is_squad_table(rows: list) -> bool:
    if not rows:
        return False
    header_text = " ".join(rows[0]).lower()
    return any(word in header_text for word in ("pos", "position", "nat", "player", "name"))


# ---------------------------------------------------------------------------
# Parsers for each block type
# ---------------------------------------------------------------------------

def _parse_results_matrix(
    rows: list, league_id: str, season: str, source_id: str, url: str
) -> list[dict]:
    body = rows[1:]
    teams = [_clean_cell(row[0]) for row in body]
    result_rows: list[dict] = []
    for i, row in enumerate(body):
        for j, cell in enumerate(row[1:]):
            if i == j:
                continue
            m = SCORE_RE.match(_clean_cell(cell))
            if not m:
                continue
            result_rows.append(
                {
                    "_row_type": "stg_match",
                    "league_id": league_id,
                    "season": season,
                    "home_team_raw": teams[i],
                    "away_team_raw": teams[j],
                    "home_goals": int(m.group(1)),
                    "away_goals": int(m.group(2)),
                    "match_date": None,       # Wikipedia matrix has no dates
                    "round": None,
                    "status": "played",
                    "source_id": source_id,
                    "source_url": url,
                }
            )
    return result_rows


def _parse_league_table(
    rows: list, league_id: str, season: str, source_id: str, url: str
) -> list[dict]:
    if not rows:
        return []
    header = [_clean_cell(h).lower() for h in rows[0]]
    result_rows: list[dict] = []
    for row in rows[1:]:
        if len(row) < 2:
            continue
        cells = [_clean_cell(c) for c in row]
        row_dict: dict[str, Any] = {
            "_row_type": "stg_standing",
            "league_id": league_id,
            "season": season,
            "source_id": source_id,
            "source_url": url,
        }
        for i, col in enumerate(header):
            if i < len(cells):
                row_dict[col] = cells[i]
        result_rows.append(row_dict)
    return result_rows


def _parse_squad_table(
    rows: list, league_id: str, season: str, source_id: str, url: str, section: str
) -> list[dict]:
    if not rows:
        return []
    result_rows: list[dict] = []
    header = [_clean_cell(h).lower() for h in rows[0]]
    for row in rows[1:]:
        if len(row) < 2:
            continue
        cells = [_clean_cell(c) for c in row]
        row_dict: dict[str, Any] = {
            "_row_type": "stg_squad",
            "league_id": league_id,
            "season": season,
            "team_raw": section,
            "source_id": source_id,
            "source_url": url,
        }
        for i, col in enumerate(header):
            if i < len(cells):
                row_dict[col] = cells[i]
        result_rows.append(row_dict)
    return result_rows


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse(raw_item: dict) -> list[dict]:
    """
    Parse one RawPageItem and return a list of StagingRow dicts.
    Returns an empty list if the block is unrecognised or empty.
    """
    if raw_item.get("block_type") != "table":
        return []

    rows: list = raw_item.get("payload") or []
    if not rows:
        return []

    league_id = raw_item.get("league_id", "")
    season = raw_item.get("season", "")
    source_id = raw_item.get("source_id", "wikipedia_season")
    url = raw_item.get("url", "")
    section = raw_item.get("section", "")

    if _is_results_matrix(rows):
        return _parse_results_matrix(rows, league_id, season, source_id, url)

    if _is_league_table(rows):
        return _parse_league_table(rows, league_id, season, source_id, url)

    if _is_squad_table(rows):
        return _parse_squad_table(rows, league_id, season, source_id, url, section)

    return []
