"""
Load Wikipedia season-page leaderboards (top scorers, assists, clean sheets,
cards) for every scraped league into staging.players + player_season_stats.

Usage:
    python loaders/load_season_player_stats.py
    python loaders/load_season_player_stats.py --league EGY_PL
    python loaders/load_season_player_stats.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "loaders"))
load_dotenv(ROOT / ".env", override=True)

from parse_players import as_int, clean_name, is_person_name, player_id

DSN = (
    f"host={os.environ['POSTGRES_HOST']} port={os.environ['POSTGRES_PORT']} "
    f"dbname={os.environ['POSTGRES_DB']} user={os.environ['POSTGRES_USER']} "
    f"password={os.environ['POSTGRES_PASSWORD']}"
)

SKIP_SECTIONS = (
    "hat-trick",
    "hattrick",
    "foreign player",
    "monthly",
    "award",
    "personnel",
    "manager",
    "stadium",
    "attendance",
    "positions by",
    "kits",
    "team of the",
    "play-off",
    "playoff",
    "allocation",
    "schedule",
    "round",
    "group",
    "knockout",
    "quarter",
    "semi-final",
    "fixture",
)

PLAYER_HEADERS = {"player", "name", "goalscorer", "goalkeeper"}
CLUB_HEADERS = {"club", "team", "for"}
GOALS_HEADERS = {"goals", "goal"}
ASSIST_HEADERS = {"assists", "assist"}
CS_HEADERS = {"clean sheets", "clean sheet"}
APPS_HEADERS = {"matches", "matches played", "apps", "appearances"}
SKIP_HEADERS = {"rank", "#", "pos", "ref", "ref.", "refs", "ref(s)", "date", "result", "score"}


def _norm_header(cell: str) -> str:
    text = re.sub(r"\[.*?\]", "", cell or "")
    text = re.sub(r"\.mw-parser-output.*", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _norm_season(season: str) -> str:
    return (season or "").replace("–", "-").replace("—", "-")


def classify_section(section: str) -> str | None:
    s = _norm_header(section)
    if not s:
        return None
    if any(token in s for token in SKIP_SECTIONS):
        return None
    if "assist" in s:
        return "assists"
    if "yellow" in s:
        return "yellow_cards"
    if "red card" in s:
        return "red_cards"
    if "clean sheet" in s or ("goalkeeper" in s and "clean" in s):
        return "clean_sheets"
    if any(token in s for token in ("top scor", "goalscor", "scoring")):
        return "goals"
    if s == "goals":
        return "goals"
    return None


def classify_header(header: list[str]) -> str | None:
    labels = {_norm_header(h) for h in header}
    if labels & ASSIST_HEADERS:
        return "assists"
    if labels & CS_HEADERS:
        return "clean_sheets"
    if labels & GOALS_HEADERS:
        return "goals"
    if any(label.startswith("md") for label in labels):
        return "goals"
    return None


def _col_index(header: list[str], names: set[str]) -> int | None:
    for i, cell in enumerate(header):
        if _norm_header(cell) in names:
            return i
    return None


def parse_table(header: list[str], body: list[list], default_stat: str) -> list[dict]:
    player_i = _col_index(header, PLAYER_HEADERS)
    club_i = _col_index(header, CLUB_HEADERS)
    goals_i = _col_index(header, GOALS_HEADERS)
    assist_i = _col_index(header, ASSIST_HEADERS)
    cs_i = _col_index(header, CS_HEADERS)
    apps_i = _col_index(header, APPS_HEADERS)
    md_indexes = [
        i for i, cell in enumerate(header) if re.fullmatch(r"md\d+|qf\d*|sf\d*|f", _norm_header(cell))
    ]

    if player_i is None:
        # Rank | Player | Club | Goals  without a recognised player header
        if len(header) >= 3:
            player_i = 1
            club_i = 2 if club_i is None else club_i

    rows_out: list[dict] = []
    for raw in body:
        cells = [clean_name(str(c)) for c in raw]
        if player_i is None or player_i >= len(cells):
            continue
        name = cells[player_i]
        if not is_person_name(name):
            continue
        club = cells[club_i] if club_i is not None and club_i < len(cells) else ""

        stat_type = default_stat
        value = None
        if default_stat == "assists" and assist_i is not None and assist_i < len(cells):
            value = as_int(cells[assist_i])
        elif default_stat == "clean_sheets" and cs_i is not None and cs_i < len(cells):
            value = as_int(cells[cs_i])
        elif goals_i is not None and goals_i < len(cells):
            value = as_int(cells[goals_i])
            if default_stat == "goals":
                stat_type = "goals"
        elif md_indexes:
            value = sum(as_int(cells[i]) or 0 for i in md_indexes if i < len(cells))
            stat_type = "goals"
        else:
            # last numeric cell that is not rank
            for cell in reversed(cells):
                if re.fullmatch(r"\d+", cell) and cell != cells[0]:
                    value = int(cell)
                    break

        if not value or value <= 0:
            continue

        appearances = None
        if apps_i is not None and apps_i < len(cells):
            appearances = as_int(cells[apps_i])

        position = {
            "clean_sheets": "Goalkeeper",
            "assists": "Midfielder",
            "goals": "Forward",
        }.get(stat_type)

        rows_out.append(
            {
                "player_name": name,
                "club_raw": club,
                "stat_type": stat_type,
                "stat_value": value,
                "appearances": appearances,
                "position": position,
            }
        )
    return rows_out


def latest_jsonl(raw_dir: Path, league_filter: str | None) -> list[Path]:
    latest: dict[tuple[str, str], Path] = {}
    base = raw_dir / "source=wikipedia_season"
    for path in base.glob("league=*/season=*/run=*.jsonl"):
        league_id = path.parts[-3].split("=", 1)[1]
        season = path.parts[-2].split("=", 1)[1]
        if league_filter and league_id != league_filter:
            continue
        key = (league_id, season)
        if key not in latest or path.name > latest[key].name:
            latest[key] = path
    return list(latest.values())


def collect(raw_dir: Path, league_filter: str | None) -> list[dict]:
    records: list[dict] = []
    for path in latest_jsonl(raw_dir, league_filter):
        league_id = path.parts[-3].split("=", 1)[1]
        season = _norm_season(path.parts[-2].split("=", 1)[1])
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                raw = json.loads(line)
                rows = raw.get("payload") or []
                if len(rows) < 2:
                    continue
                section = raw.get("section") or ""
                stat = classify_section(section) or classify_header(rows[0])
                if not stat:
                    continue
                url = raw.get("url") or raw.get("source_url") or ""
                for item in parse_table(rows[0], rows[1:], stat):
                    item.update(league_id=league_id, season=season, source_url=url)
                    records.append(item)
    return records


def write(records: list[dict], dry_run: bool) -> None:
    by_league: dict[str, int] = {}
    for row in records:
        by_league[row["league_id"]] = by_league.get(row["league_id"], 0) + 1
    print(f"Parsed {len(records)} leaderboard rows")
    for lid, n in sorted(by_league.items()):
        print(f"  {lid:12} {n:4d}")
    if dry_run or not records:
        return

    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            "ALTER TABLE staging.player_season_stats "
            "ADD COLUMN IF NOT EXISTS league_id TEXT"
        )
        leagues = sorted({row["league_id"] for row in records})
        cur.execute(
            "DELETE FROM staging.player_season_stats WHERE league_id = ANY(%s)",
            (leagues,),
        )

        stats = 0
        players = 0
        for row in records:
            pid = player_id(row["player_name"], None)
            cur.execute(
                """
                INSERT INTO staging.players
                    (player_id, wiki_title, full_name, position, current_club, source_url)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (player_id) DO UPDATE SET
                    position = COALESCE(EXCLUDED.position, staging.players.position),
                    current_club = COALESCE(EXCLUDED.current_club, staging.players.current_club)
                """,
                (
                    pid,
                    row["player_name"],
                    row["player_name"],
                    row["position"],
                    row["club_raw"] or None,
                    row["source_url"] or "wikipedia_season",
                ),
            )
            players += 1
            cur.execute(
                """
                INSERT INTO staging.player_season_stats
                    (player_name, season, club_raw, stat_type, stat_value, source_url, league_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (player_name, season, stat_type, club_raw) DO UPDATE SET
                    stat_value = EXCLUDED.stat_value,
                    league_id = COALESCE(EXCLUDED.league_id, staging.player_season_stats.league_id),
                    source_url = EXCLUDED.source_url
                """,
                (
                    row["player_name"],
                    row["season"],
                    row["club_raw"] or "",
                    row["stat_type"],
                    row["stat_value"],
                    row["source_url"] or "wikipedia_season",
                    row["league_id"],
                ),
            )
            stats += 1
            if row.get("appearances"):
                cur.execute(
                    """
                    INSERT INTO staging.player_season_stats
                        (player_name, season, club_raw, stat_type, stat_value, source_url, league_id)
                    VALUES (%s, %s, %s, 'appearances', %s, %s, %s)
                    ON CONFLICT (player_name, season, stat_type, club_raw) DO UPDATE SET
                        stat_value = EXCLUDED.stat_value,
                        league_id = COALESCE(EXCLUDED.league_id, staging.player_season_stats.league_id)
                    """,
                    (
                        row["player_name"],
                        row["season"],
                        row["club_raw"] or "",
                        row["appearances"],
                        row["source_url"] or "wikipedia_season",
                        row["league_id"],
                    ),
                )

        conn.commit()
        print(f"Upserted players: {players}")
        print(f"Upserted season stats: {stats}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", help="Only process this league_id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    records = collect(ROOT / "data" / "raw", args.league)
    write(records, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
