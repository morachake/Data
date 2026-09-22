"""
load_raw.py — load wikipedia_season JSONL files into raw.wiki_tables.

Handles both layouts:
  Legacy (Phase 0 transition):
    data/raw/wiki_psl_seasons/<timestamp>.jsonl
    Item keys: source, source_url, season, table_index, section, rows, scraped_at

  New Hive layout (Phase 0+):
    data/raw/source=wikipedia_season/league=<id>/season=<label>/run=<ts>_<id>.jsonl
    Item keys: RawPageItem fields (source_id, url, season, block_index, section,
               payload, fetched_at, ...)

In Phase 1, this loader is superseded by parsers/wikipedia_season.py which
writes directly into the new staging tables.  Keep this file until that
transition is complete.
"""

import json
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

DSN = (
    f"host={os.environ['POSTGRES_HOST']} port={os.environ['POSTGRES_PORT']} "
    f"dbname={os.environ['POSTGRES_DB']} user={os.environ['POSTGRES_USER']} "
    f"password={os.environ['POSTGRES_PASSWORD']}"
)


def _normalise(item: dict) -> dict | None:
    """Translate both item formats to the raw.wiki_tables column set."""
    # New RawPageItem format
    if "source_id" in item:
        if item.get("block_type") != "table":
            return None  # only load table blocks
        return {
            "source": item["source_id"],
            "source_url": item["url"],
            "season": item["season"],
            "table_index": item.get("block_index", 0),
            "section": item.get("section", ""),
            "rows": item["payload"],
            "scraped_at": item["fetched_at"],
        }
    # Legacy format
    if "source" in item and "rows" in item:
        return item
    return None


def load_file(path: Path) -> int:
    count = 0
    with psycopg.connect(DSN) as conn, conn.cursor() as cur, path.open(encoding="utf-8") as f:
        for line in f:
            raw = json.loads(line)
            normalised = _normalise(raw)
            if normalised is None:
                continue
            cur.execute(
                """INSERT INTO raw.wiki_tables
                   (source, source_url, season, table_index, section, rows, scraped_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                (
                    normalised["source"],
                    normalised["source_url"],
                    normalised["season"],
                    normalised["table_index"],
                    normalised["section"],
                    Jsonb(normalised["rows"]),
                    normalised["scraped_at"],
                ),
            )
            count += 1
    return count


def _find_files(folder: Path) -> list[Path]:
    """Return all JSONL files under folder, including Hive sub-directories."""
    return sorted(folder.rglob("*.jsonl"))


if __name__ == "__main__":
    # Accept an explicit folder; default to scanning both old and new paths.
    if len(sys.argv) > 1:
        folder = Path(sys.argv[1])
        files = _find_files(folder)
    else:
        # Legacy flat directory
        legacy = ROOT / "data" / "raw" / "wiki_psl_seasons"
        # New Hive directory
        hive = ROOT / "data" / "raw" / "source=wikipedia_season"
        files = []
        if legacy.exists():
            files += _find_files(legacy)
        if hive.exists():
            files += _find_files(hive)

    if not files:
        raise SystemExit(
            "No JSONL files found. Run `scrapy crawl wiki_psl_seasons` first."
        )

    total = 0
    for f in files:
        n = load_file(f)
        if n:
            print(f"  {f.relative_to(ROOT)}: {n} rows")
            total += n
    print(f"Total: {total} rows loaded into raw.wiki_tables")
