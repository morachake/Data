"""
scrape_stubs.py  —  Fetch DOB/bio for stub players (no individual page scraped yet).

Usage:
    python loaders/scrape_stubs.py                   # use data/stub_player_pages.txt
    python loaders/scrape_stubs.py --file <path>     # custom list (one wiki title per line)
    python loaders/scrape_stubs.py --limit 50        # stop after N pages

Reads a plain-text file of Wikipedia titles, fetches each page, extracts player
info using the same ingestion helpers as the Scrapy spider, then upserts into
staging.players.  Politely rate-limited to ~1 req/s.

Run this after the main wiki_psl_players spider to fill in players that appeared
in squad tables but never had their personal pages visited.
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

import psycopg
import requests
from dotenv import load_dotenv
from scrapy.http import HtmlResponse

# ── Path setup ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ingestion"))

load_dotenv(ROOT / ".env", override=True)

from ingestion.player_extract import (  # noqa: E402
    career_rows,
    extract_injuries,
    first_bio,
    infobox_image,
    infobox_map,
    looks_like_footballer,
    wikidata_id as extract_wikidata_id,
)

# ── Re-use parse_players helpers without a circular import ──────────────────
sys.path.insert(0, str(ROOT / "loaders"))
from parse_players import (  # noqa: E402
    clean_name,
    extract_dob_from_bio,
    extract_nationality_from_bio,
    is_person_name,
    pick,
    player_id,
)

DSN = (
    f"host={os.environ['POSTGRES_HOST']} port={os.environ['POSTGRES_PORT']} "
    f"dbname={os.environ['POSTGRES_DB']} user={os.environ['POSTGRES_USER']} "
    f"password={os.environ['POSTGRES_PASSWORD']}"
)

DEFAULT_STUB_FILE = ROOT / "data" / "stub_player_pages.txt"
WIKI_API = "https://en.wikipedia.org/wiki/{}"
HEADERS = {
    "User-Agent": (
        "AfricanFootballDataBot/1.0 (academic; non-commercial; "
        "https://github.com/moracha/african-football-data) "
        "Python-requests"
    )
}
DELAY_SECS = 1.2  # polite crawl delay


def fetch_page(title: str) -> HtmlResponse | None:
    url = WIKI_API.format(quote(title.replace(" ", "_")))
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return HtmlResponse(url=url, body=r.content, encoding="utf-8")
    except Exception as exc:
        print(f"  ⚠  {title}: {exc}")
        return None


def scrape_and_upsert(titles: list[str], conn: psycopg.Connection) -> dict:
    stats = {"fetched": 0, "saved": 0, "skipped_not_footballer": 0, "skipped_no_page": 0}
    cur = conn.cursor()

    for i, title in enumerate(titles, 1):
        print(f"[{i}/{len(titles)}] {title}", end=" … ", flush=True)
        resp = fetch_page(title)
        if resp is None:
            print("404")
            stats["skipped_no_page"] += 1
            time.sleep(DELAY_SECS)
            continue

        stats["fetched"] += 1
        info = infobox_map(resp)
        bio = first_bio(resp)
        career = career_rows(resp)

        # Reject club/non-footballer pages
        if "founded" in info or "ground" in info:
            print("club page, skip")
            stats["skipped_not_footballer"] += 1
            time.sleep(DELAY_SECS)
            continue
        if not looks_like_footballer(info, bio, career):
            print("not footballer")
            stats["skipped_not_footballer"] += 1
            time.sleep(DELAY_SECS)
            continue

        heading = " ".join(resp.css("h1#firstHeading ::text").getall()).strip()
        resolved_title = heading or title

        wid = extract_wikidata_id(resp)
        pid = player_id(resolved_title, wid)
        full_name = clean_name(pick(info, "full name", "name") or resolved_title)
        nationality = pick(info, "nationality", "national team") or extract_nationality_from_bio(bio)
        raw_dob = pick(info, "date of birth") or extract_dob_from_bio(bio)
        image_url = infobox_image(resp)

        # Store into raw for record-keeping
        body_text = " ".join(
            resp.css("div.mw-parser-output p::text, div.mw-parser-output p *:not(sup)::text").getall()
        )
        payload = {
            "kind": "player_profile",
            "wiki_title": resolved_title,
            "source_url": resp.url,
            "discovered_from": "scrape_stubs",
            "wikidata_id": wid,
            "image_url": image_url,
            "bio": bio,
            "infobox": info,
            "career": career,
            "injuries": extract_injuries(body_text),
        }
        cur.execute(
            """INSERT INTO raw.wiki_player_pages (kind, payload, scraped_at)
               VALUES (%s, %s, now())
               ON CONFLICT DO NOTHING""",
            ("player_profile", json.dumps(payload)),
        )

        # Upsert into staging.players
        cur.execute(
            """INSERT INTO staging.players
               (player_id, wiki_title, full_name, date_of_birth, nationality,
                bio, image_url, wikidata_id, source_url)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (player_id) DO UPDATE SET
                 date_of_birth = COALESCE(EXCLUDED.date_of_birth,
                                          staging.players.date_of_birth),
                 nationality   = COALESCE(EXCLUDED.nationality,
                                          staging.players.nationality),
                 bio           = COALESCE(EXCLUDED.bio, staging.players.bio),
                 image_url     = COALESCE(EXCLUDED.image_url, staging.players.image_url),
                 wikidata_id   = COALESCE(EXCLUDED.wikidata_id, staging.players.wikidata_id)""",
            (pid, resolved_title, full_name, raw_dob, nationality,
             bio, image_url, wid, resp.url),
        )
        conn.commit()
        stats["saved"] += 1
        dob_str = raw_dob or "—"
        nat_str = nationality or "—"
        print(f"✓  DOB={dob_str}  Nat={nat_str}")
        time.sleep(DELAY_SECS)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Scrape stub player Wikipedia pages")
    parser.add_argument("--file", default=str(DEFAULT_STUB_FILE))
    parser.add_argument("--limit", type=int, default=0, help="Stop after N pages (0=all)")
    args = parser.parse_args()

    stub_file = Path(args.file)
    if not stub_file.exists():
        print(f"Stub file not found: {stub_file}")
        print("Run the SQL export first:  make stubs  or  python loaders/export_stubs.py")
        sys.exit(1)

    titles = [line.strip() for line in stub_file.read_text().splitlines() if line.strip()]
    if args.limit:
        titles = titles[: args.limit]

    print(f"Scraping {len(titles)} stub player pages …\n")
    with psycopg.connect(DSN) as conn:
        stats = scrape_and_upsert(titles, conn)

    print(
        f"\nDone: {stats['fetched']} fetched, "
        f"{stats['saved']} saved, "
        f"{stats['skipped_not_footballer']} non-footballer, "
        f"{stats['skipped_no_page']} 404."
    )
    print("\nNext: run  dbt build --select core.player+ shortlist  to refresh age data.")


if __name__ == "__main__":
    main()
