"""
parsers/rsssf_tables.py

Parses RawPageItem blocks (block_type='text') scraped from RSSSF season pages.

RSSSF match-result format (many variants):
  "Team A - Team B  2:1"
  "Team A v Team B  2-1 (1-0)"
  "Team A  2-1  Team B"
  "[date]  Team A - Team B  2:1  (venue)"

Match lines may be preceded by a section header like:
  "1. Round"  or  "Matchday 3"  or  "Week 12"

The spider stores the whole page text with season='all'; this parser splits by
season marker and returns rows tagged with the specific season.

Season marker detection: lines matching a 4-digit year or "YYYY-YY" heading.

Entry point: parse(raw_item) -> list[dict]
"""

import re
from typing import Any

from parsers.common.text import clean, normalise_dashes

# Match result line patterns (order matters — most specific first).
# Captures: home, away, home_goals, away_goals.
_RESULT_PATTERNS = [
    # "Team A - Team B  2:1" or "Team A - Team B 2-1 (1-0)"
    re.compile(
        r"^(?P<home>.+?)\s+[-–v]\s+(?P<away>.+?)\s+(?P<hg>\d+)[-:–](?P<ag>\d+)",
        re.IGNORECASE,
    ),
    # "Team A  2-1  Team B"
    re.compile(
        r"^(?P<home>.+?)\s+(?P<hg>\d+)[-:–](?P<ag>\d+)\s+(?P<away>.+)$",
        re.IGNORECASE,
    ),
]

# Season heading: "2024-25" or "2024/25" or plain "2024"
_SEASON_HEADING = re.compile(
    r"^\s*(?:season\s+)?(?P<y1>\d{4})[-/](?P<y2>\d{2,4})\b"
    r"|^\s*(?P<year>19\d{2}|20\d{2})\s*$",
    re.IGNORECASE,
)

# Round / matchday heading
_ROUND_HEADING = re.compile(
    r"^\s*(?:round|matchday|week|jour(?:née)?|tour|round of|matchweek)\s*(?P<n>\d+)",
    re.IGNORECASE,
)

# Date prefix: "12 Aug 2024" etc. (stripped before result matching)
_DATE_PREFIX = re.compile(
    r"^\s*\d{1,2}[-/.\s][A-Za-z]{3,9}[-/.\s]\d{4}\b\s*"
)


def _normalise_season(y1: str, y2: str) -> str:
    """Convert "2024" + "25" → "2024-25"."""
    if len(y2) == 4:
        return f"{y1}-{y2[2:]}"
    return f"{y1}-{y2}"


def _split_into_seasons(text: str) -> dict[str, list[str]]:
    """
    Split page text into per-season buckets.
    Returns {season_label: [lines]}.
    """
    buckets: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        m = _SEASON_HEADING.match(line)
        if m:
            if m.group("year"):
                yr = m.group("year")
                # Single year — convert to "YYYY-YY" using next year's last two digits
                current = f"{yr}-{str(int(yr)+1)[2:]}"
            else:
                current = _normalise_season(m.group("y1"), m.group("y2"))
            buckets.setdefault(current, [])
        elif current is not None:
            buckets[current].append(line)
    return buckets


def _parse_match_line(line: str, round_: str | None, season: str, league_id: str, source_id: str, url: str) -> dict | None:
    # Strip leading date
    line = _DATE_PREFIX.sub("", line).strip()
    # Strip trailing venue / attendance info in parentheses
    line = re.sub(r"\([^)]*\)\s*$", "", line).strip()
    # Strip footnotes
    line = re.sub(r"\[[^\]]*\]", "", line).strip()

    line = normalise_dashes(line)

    for pat in _RESULT_PATTERNS:
        m = pat.match(line)
        if m:
            home = clean(m.group("home"))
            away = clean(m.group("away"))
            hg = int(m.group("hg"))
            ag = int(m.group("ag"))
            if not home or not away:
                continue
            return {
                "_row_type": "stg_match",
                "league_id": league_id,
                "season": season,
                "home_team_raw": home,
                "away_team_raw": away,
                "home_goals": hg,
                "away_goals": ag,
                "match_date": None,    # TODO: extract date from prefix
                "round": round_,
                "status": "played",
                "source_id": source_id,
                "source_url": url,
            }
    return None


def _parse_season_lines(
    lines: list[str], season: str, league_id: str, source_id: str, url: str
) -> list[dict]:
    rows: list[dict] = []
    current_round: str | None = None
    for line in lines:
        round_m = _ROUND_HEADING.match(line)
        if round_m:
            current_round = round_m.group("n")
            continue
        row = _parse_match_line(line, current_round, season, league_id, source_id, url)
        if row:
            rows.append(row)
    return rows


def parse(raw_item: dict) -> list[dict]:
    """
    Parse one RawPageItem (block_type='text') from RSSSF.
    Returns stg_match rows for every season covered by the page.
    """
    if raw_item.get("block_type") != "text":
        return []

    payload = raw_item.get("payload") or {}
    text: str = payload.get("text", "")
    if not text:
        return []

    league_id = raw_item.get("league_id", "")
    source_id = raw_item.get("source_id", "rsssf_tables")
    url = raw_item.get("url", "")

    # If the spider already tagged a specific season, only parse that one.
    requested_season = raw_item.get("season") if raw_item.get("season") != "all" else None

    season_buckets = _split_into_seasons(text)
    if not season_buckets:
        # No season headers found — treat the whole page as one season blob.
        season_buckets = {requested_season or "unknown": text.splitlines()}

    rows: list[dict] = []
    for season, lines in season_buckets.items():
        if requested_season and season != requested_season:
            continue
        rows.extend(_parse_season_lines(lines, season, league_id, source_id, url))

    return rows
