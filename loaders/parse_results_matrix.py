import json
import os
import re
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

DSN = (
    f"host={os.environ['POSTGRES_HOST']} port={os.environ['POSTGRES_PORT']} "
    f"dbname={os.environ['POSTGRES_DB']} user={os.environ['POSTGRES_USER']} "
    f"password={os.environ['POSTGRES_PASSWORD']}"
)
SCORE = re.compile(r"^(\d+)\s*[–-]\s*(\d+)$")
FOOTNOTE = re.compile(r"\[.*?\]")


def clean(cell: str) -> str:
    return FOOTNOTE.sub("", cell).strip()


def as_rows(value):
    if isinstance(value, str):
        return json.loads(value)
    return value


def score_count(rows) -> int:
    body = rows[1:]
    return sum(1 for r in body for c in r[1:] if SCORE.match(clean(c)))


def is_results_matrix(rows) -> bool:
    if len(rows) < 11:
        return False
    header, body = rows[0], rows[1:]
    n = len(body)
    if len(header) - 1 != n:
        return False
    scores = score_count(rows)
    complete = n * (n - 1)
    # Finished seasons are mostly filled; the current season is still sparse.
    return scores >= 0.8 * complete or scores >= n


def unpivot(rows):
    body = rows[1:]
    teams = [clean(r[0]) for r in body]
    for i, row in enumerate(body):
        for j, cell in enumerate(row[1:]):
            if i == j:
                continue
            m = SCORE.match(clean(cell))
            if m:
                yield teams[i], teams[j], int(m.group(1)), int(m.group(2))


def main():
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        # Latest scrape of each season only
        cur.execute("""
            SELECT DISTINCT ON (season, table_index) season, table_index, rows, source_url
            FROM raw.wiki_tables
            ORDER BY season, table_index, scraped_at DESC
        """)
        found = {}
        for season, _, rows, url in cur.fetchall():
            rows = as_rows(rows)
            if not is_results_matrix(rows):
                continue
            scores = score_count(rows)
            previous = found.get(season)
            if previous is None or scores > previous[0]:
                found[season] = (scores, rows, url)

        for season, (_, rows, url) in found.items():
            cur.execute("DELETE FROM staging.wiki_results WHERE season = %s", (season,))
            matches = list(unpivot(rows))
            cur.executemany(
                """INSERT INTO staging.wiki_results
                   (season, home_team_raw, away_team_raw, home_goals, away_goals, source_url)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                [(season, h, a, hg, ag, url) for h, a, hg, ag in matches],
            )
            print(f"{season}: {len(matches)} matches")


if __name__ == "__main__":
    main()
