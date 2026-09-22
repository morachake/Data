"""
loaders/load_jsonl.py — Parse all Hive-partitioned JSONL raw files and
insert match/standing rows into staging tables.

Usage:
    python loaders/load_jsonl.py                 # process all leagues
    python loaders/load_jsonl.py --league EGY_PL # single league
    python loaders/load_jsonl.py --dry-run       # count rows, no insert

The script is idempotent: it truncates staging data for each
(league_id, season, source_id) triple before re-inserting, so it is safe
to run multiple times.
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env", override=True)

from parsers.wikipedia_season import parse  # noqa: E402


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def dsn() -> str:
    return (
        f"host={os.environ['POSTGRES_HOST']} port={os.environ['POSTGRES_PORT']} "
        f"dbname={os.environ['POSTGRES_DB']} user={os.environ['POSTGRES_USER']} "
        f"password={os.environ['POSTGRES_PASSWORD']}"
    )


# ---------------------------------------------------------------------------
# Batch collector
# ---------------------------------------------------------------------------

def collect_rows(raw_dir: Path, league_filter: str | None = None):
    """
    Walk the Hive directory tree and parse every JSONL file.
    Returns (match_rows, standing_rows) where each row is a dict.
    """
    match_rows: list[dict] = []
    standing_rows: list[dict] = []
    files_seen = 0
    files_skipped = 0

    pattern = "source=wikipedia_season"
    base = raw_dir / pattern
    if not base.exists():
        print(f"[WARN] Raw dir not found: {base}")
        return match_rows, standing_rows

    for jsonl_path in sorted(base.glob("**/run=*.jsonl")):
        # Extract league_id from path: .../league=EGY_PL/...
        parts = jsonl_path.parts
        league_part = next((p for p in parts if p.startswith("league=")), None)
        if not league_part:
            continue
        league_id = league_part.split("=", 1)[1]

        if league_filter and league_id != league_filter:
            files_skipped += 1
            continue

        files_seen += 1
        with open(jsonl_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue

                run_id = raw.get("run_id", "")
                for row in parse(raw):
                    row["run_id"] = run_id
                    if row["_row_type"] == "stg_match":
                        match_rows.append(row)
                    elif row["_row_type"] == "stg_standing":
                        standing_rows.append(row)

    print(f"Files read: {files_seen}  skipped: {files_skipped}")
    return match_rows, standing_rows


# ---------------------------------------------------------------------------
# Standing row normaliser
# ---------------------------------------------------------------------------

# Map common Wikipedia column header variants → DB column names
_STANDING_COL_MAP: dict[str, str] = {
    "pos":       "position",
    "#":         "position",
    "team":      "team_raw",
    "club":      "team_raw",
    "pld":       "played",
    "pl":        "played",
    "mp":        "played",
    "p":         "played",
    "w":         "won",
    "d":         "drawn",
    "l":         "lost",
    "gf":        "goals_for",
    "f":         "goals_for",
    "for":       "goals_for",
    "ga":        "goals_against",
    "a":         "goals_against",
    "against":   "goals_against",
    "pts":       "points",
    "pt":        "points",
    "points":    "points",
}


def _to_int(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _normalise_standing(row: dict) -> dict | None:
    """Map parser output → staging.stg_standing column names. Returns None to skip."""
    out: dict = {
        "league_id":      row.get("league_id", ""),
        "season":         row.get("season", ""),
        "team_raw":       None,
        "position":       None,
        "played":         None,
        "won":            None,
        "drawn":          None,
        "lost":           None,
        "goals_for":      None,
        "goals_against":  None,
        "points":         None,
        "source_id":      row.get("source_id", "wikipedia_season"),
        "source_url":     row.get("source_url", ""),
        "run_id":         row.get("run_id", ""),
    }
    for key, val in row.items():
        mapped = _STANDING_COL_MAP.get(key.strip().lower())
        if mapped and val is not None and str(val).strip():
            if mapped == "team_raw":
                out["team_raw"] = str(val).strip()
            else:
                out[mapped] = _to_int(val)

    # Skip rows that don't have a team name or points (header/footer rows)
    if not out["team_raw"] or out["points"] is None:
        return None
    return out


# ---------------------------------------------------------------------------
# DB writer
# ---------------------------------------------------------------------------

MATCH_COLS = (
    "league_id", "season", "home_team_raw", "away_team_raw",
    "home_goals", "away_goals", "match_date", "round", "status",
    "source_id", "source_url", "run_id",
)

STANDING_COLS = (
    "league_id", "season", "team_raw", "position",
    "played", "won", "drawn", "lost", "goals_for", "goals_against", "points",
    "source_id", "source_url", "run_id",
)


def write_rows(
    match_rows: list[dict],
    standing_rows: list[dict],
    dry_run: bool = False,
) -> None:
    # ── Group by (league_id, season, source_id) for targeted truncation
    match_groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in match_rows:
        key = (r["league_id"], r["season"], r.get("source_id", "wikipedia_season"))
        match_groups[key].append(r)

    standing_groups: dict[tuple, list[dict]] = defaultdict(list)
    normalised_standing_rows: list[dict] = []
    for r in standing_rows:
        norm = _normalise_standing(r)
        if norm:
            normalised_standing_rows.append(norm)
            key = (norm["league_id"], norm["season"], norm.get("source_id", "wikipedia_season"))
            standing_groups[key].append(norm)

    total_m = sum(len(v) for v in match_groups.values())
    total_s = len(normalised_standing_rows)
    print(f"Match rows to write:    {total_m:,}")
    print(f"Standing rows to write: {total_s:,}")

    if dry_run:
        print("[DRY RUN] No data written.")
        return

    with psycopg.connect(dsn()) as conn:
        with conn.cursor() as cur:
            # ── Matches ──────────────────────────────────────────────────────
            for (lid, season, src), rows in sorted(match_groups.items()):
                cur.execute(
                    "DELETE FROM staging.stg_match "
                    "WHERE league_id = %s AND season = %s AND source_id = %s",
                    (lid, season, src),
                )
                col_list = ", ".join(MATCH_COLS)
                placeholders = ", ".join(["%s"] * len(MATCH_COLS))
                cur.executemany(
                    f"INSERT INTO staging.stg_match ({col_list}) VALUES ({placeholders})",
                    [tuple(r.get(c) for c in MATCH_COLS) for r in rows],
                )
                print(f"  stg_match  {lid}/{season}: {len(rows):4d} rows")

            # ── Standings ────────────────────────────────────────────────────
            for (lid, season, src), rows in sorted(standing_groups.items()):
                cur.execute(
                    "DELETE FROM staging.stg_standing "
                    "WHERE league_id = %s AND season = %s AND source_id = %s",
                    (lid, season, src),
                )
                col_list = ", ".join(STANDING_COLS)
                placeholders = ", ".join(["%s"] * len(STANDING_COLS))
                cur.executemany(
                    f"INSERT INTO staging.stg_standing ({col_list}) VALUES ({placeholders})",
                    [tuple(r.get(c) for c in STANDING_COLS) for r in rows],
                )
                print(f"  stg_standing {lid}/{season}: {len(rows):4d} rows")

        conn.commit()

    print("Done.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--league", help="Only process this league_id")
    ap.add_argument("--dry-run", action="store_true", help="Count rows without writing")
    args = ap.parse_args()

    raw_dir = ROOT / "data" / "raw"
    print(f"Scanning {raw_dir} ...")
    match_rows, standing_rows = collect_rows(raw_dir, league_filter=args.league)
    print(f"Parsed  match rows: {len(match_rows):,}")
    print(f"Parsed  standing rows: {len(standing_rows):,}")
    write_rows(match_rows, standing_rows, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
