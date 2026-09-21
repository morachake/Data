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
        cur.execute("TRUNCATE raw.wiki_player_pages")
        for line in f:
            item = json.loads(line)
            cur.execute(
                """INSERT INTO raw.wiki_player_pages (kind, payload, source_url)
                   VALUES (%s, %s, %s)""",
                (item.get("kind", "unknown"), Jsonb(item), item.get("source_url")),
            )
            count += 1
    return count


if __name__ == "__main__":
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "data/raw/wiki_psl_players")
    files = [path for path in folder.glob("*.jsonl") if path.stat().st_size > 0]
    if not files:
        raise SystemExit(f"No JSONL files found in {folder}. Run wiki_psl_players first.")
    latest = max(files, key=lambda p: p.stat().st_mtime)
    print(f"Loaded {load_file(latest)} player records from {latest}")
