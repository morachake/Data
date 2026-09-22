"""
entity_resolution/review_queue.py

CLI tool for human review of grey-zone player matches.

Usage
-----
    python -m entity_resolution.review_queue [--limit N] [--league RSA_PREM]

For each pending review:
  - Shows the two candidate names, source, score, and any DOB info.
  - Accepts 'y' (same person), 'n' (different people), or 's' (skip).
  - 'y' writes the accepted match to core.player_alias.
  - 'n' writes a rejection so the pair is not re-queued.
"""

import os
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


def run_review(limit: int = 50, league_filter: str | None = None) -> None:
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        query = """
            SELECT id, name_a, source_a, name_b, source_b, score
            FROM staging.review_queue
            WHERE status = 'pending'
            ORDER BY score DESC
            LIMIT %s
        """
        cur.execute(query, (limit,))
        rows = cur.fetchall()

    if not rows:
        print("No pending reviews. All grey-zone matches are resolved.")
        return

    print(f"\n{len(rows)} pending reviews (highest score first):\n")

    for review_id, name_a, source_a, name_b, source_b, score in rows:
        print(f"  Score: {score:.1f}")
        print(f"  A: '{name_a}' (source: {source_a})")
        print(f"  B: '{name_b}' (source: {source_b})")
        answer = input("  Same person? [y/n/s] ").strip().lower()

        if answer == "y":
            _accept(review_id, name_a, source_a, name_b, source_b, score)
        elif answer == "n":
            _reject(review_id)
        else:
            print("  Skipped.\n")


def _accept(review_id: int, name_a: str, source_a: str, name_b: str, source_b: str, score: float) -> None:
    import uuid
    from entity_resolution.name_normalise import canonical

    player_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, canonical(name_a)))
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        for name, source in [(name_a, source_a), (name_b, source_b)]:
            cur.execute("""
                INSERT INTO core.player_alias
                    (alias, source_id, player_id, method, score, resolved_at)
                VALUES (%s, %s, %s, 'manual_review', %s, now())
                ON CONFLICT (alias, source_id) DO UPDATE
                    SET player_id = EXCLUDED.player_id, resolved_at = now()
            """, (name, source, player_id, score))
        cur.execute(
            "UPDATE staging.review_queue SET status = 'accepted' WHERE id = %s",
            (review_id,),
        )
    print(f"  ✓ Accepted → player_id {player_id}\n")


def _reject(review_id: int) -> None:
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE staging.review_queue SET status = 'rejected' WHERE id = %s",
            (review_id,),
        )
    print("  ✗ Rejected.\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--league", type=str, default=None)
    args = parser.parse_args()
    run_review(limit=args.limit, league_filter=args.league)
