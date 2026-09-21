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


def load_file(path: Path) -> int:
    count = 0
    with psycopg.connect(DSN) as conn, conn.cursor() as cur, path.open(encoding="utf8") as f:
        for line in f:
            item = json.loads(line)
            cur.execute(
                """INSERT INTO raw.wiki_tables
                   (source, source_url, season, table_index, section, rows, scraped_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    item["source"],
                    item["source_url"],
                    item["season"],
                    item["table_index"],
                    item["section"],
                    Jsonb(item["rows"]),
                    item["scraped_at"],
                ),
            )
            count += 1
    return count


if __name__ == "__main__":
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "data/raw/wiki_psl_seasons")
    files = list(folder.glob("*.jsonl"))
    if not files:
        raise SystemExit(f"No JSONL files found in {folder}. Run the spider first.")
    latest = max(files, key=lambda p: p.stat().st_mtime)
    print(f"Loaded {load_file(latest)} tables from {latest}")
