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

STAT_SECTIONS = {
    "goals": "goals",
    "top scorers": "goals",
    "top goalscorers": "goals",
    "assists": "assists",
    "clean sheets": "clean_sheets",
    "yellow cards": "yellow_cards",
    "red cards": "red_cards",
}


def player_id(wiki_title: str, wikidata: str | None) -> str:
    if wikidata:
        return wikidata
    slug = re.sub(r"[^A-Z0-9]+", "_", (wiki_title or "").upper()).strip("_")
    return f"WIKI_{slug}"


def pick(info: dict, *keys: str) -> str | None:
    lower = {str(k).lower(): v for k, v in info.items()}
    for key in keys:
        if key in lower and lower[key]:
            return str(lower[key])
    return None


def as_int(value) -> int | None:
    if value is None:
        return None
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None


def clean_name(value: str | None) -> str:
    text = re.sub(r"\[\s*\d+\s*\]", "", value or "")
    return re.sub(r"\s+", " ", text).strip(" -–—")


# Suffixes that indicate a club / team name rather than a person
_CLUB_SUFFIX_RE = re.compile(
    r"\b(United|City|FC|F\.C\.|AFC|Wanderers|Rangers|Athletic|Rovers|Sporting"
    r"|Cosmos|Hotspurs|Pirates|Chiefs|Sundowns|Swallows|Arrows|Galaxy"
    r"|FCSB|AmaZulu|Sekhukhune)\b",
    re.IGNORECASE,
)


def is_person_name(value: str | None) -> bool:
    name = clean_name(value)
    if len(name) < 4 or name.lower() in {"player", "name", "total", "own goals"}:
        return False
    # Reject obvious club / team names
    if _CLUB_SUFFIX_RE.search(name):
        return False
    return bool(re.search(r"[A-Za-zÀ-ÿ]{3,}", name))


# ── Nationality extraction from bio text ─────────────────────────────────────
# Wikipedia bios open with "X is a/an <nationality> [professional] footballer"
# e.g. "Sherwyn Naicker (born 26 March 1991) is a South African former professional soccer player"
_BIO_NATIONALITY_RE = re.compile(
    r"\bis an? ([\w\s\-]+?(?:ian|an|ese|ish|i|er|nian|ean|lian|rian|ican|enian|onian|andan|golan|inian|olese|olian))\b"
    r"(?:\s+(?:former\s+)?(?:professional\s+)?(?:South\s+African\s+)?(?:football|soccer|player|professional))",
    re.IGNORECASE,
)

# Curated list of known African footballer nationalities for validation
_KNOWN_NATIONALITIES = {
    "south african", "nigerian", "ghanaian", "kenyan", "tanzanian",
    "ugandan", "zambian", "zimbabwean", "malawian", "mozambican",
    "botswanan", "namibian", "lesothan", "swazi", "congolese",
    "cameroonian", "ivorian", "senegalese", "moroccan", "algerian",
    "tunisian", "egyptian", "ethiopian", "rwandan", "burundian",
    "sudanese", "libyan", "angolan", "cape verdean", "guinean",
    "sierra leonean", "liberian", "togolese", "beninese", "malian",
    "burkinabe", "nigerien", "chadian", "gabonese", "equatorial guinean",
    "eritrean", "djiboutian", "somali", "seychellois", "mauritian",
    "malagasy", "comoran", "mozambican", "gambian",
    # European / other common in African leagues
    "french", "portuguese", "spanish", "brazilian", "argentinian",
    "uruguayan", "colombian", "dutch", "belgian", "english", "irish",
    "scottish", "swedish", "norwegian", "danish", "german", "italian",
    "greek", "austrian", "swiss", "croatian", "serbian", "bosnian",
}


_STRIP_PREFIXES = re.compile(
    r"^(retired|former|dual|professional|late|active|british|honorary)\s+",
    re.IGNORECASE,
)


# ── DOB extraction from bio text ─────────────────────────────────────────────
_MONTH_MAP = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}

# Patterns:
#   "(born 5 February 2001)"  "(born 1978)"  "(3 June 1980 –"
_BIO_DOB_PATTERNS = [
    # ISO already embedded: born 1978-03-04
    re.compile(r"\bborn[^)]*?(\d{4}-\d{2}-\d{2})", re.IGNORECASE),
    # "born DD Month YYYY" or "(DD Month YYYY)" with optional [n]
    re.compile(
        r"\bborn\s+(\d{1,2})\s+(january|february|march|april|may|june|july"
        r"|august|september|october|november|december)\s+(\d{4})",
        re.IGNORECASE,
    ),
    # "(DD Month YYYY –" death / career range bracket
    re.compile(
        r"\((\d{1,2})\s+(january|february|march|april|may|june|july"
        r"|august|september|october|november|december)\s+(\d{4})\s*[–-]",
        re.IGNORECASE,
    ),
    # born YYYY (year only)
    re.compile(r"\bborn\s+(?:c\.\s*)?(\d{4})\b", re.IGNORECASE),
]


def extract_dob_from_bio(bio: str | None) -> str | None:
    """Return ISO date string (YYYY-MM-DD or YYYY-01-01) from bio text, or None."""
    if not bio:
        return None
    for pat in _BIO_DOB_PATTERNS:
        m = pat.search(bio)
        if not m:
            continue
        groups = m.groups()
        if len(groups) == 1:
            val = groups[0]
            # ISO date already
            if re.match(r"\d{4}-\d{2}-\d{2}", val):
                return val
            # Year-only
            if re.match(r"\d{4}", val):
                return f"{val}-01-01"
        elif len(groups) == 3:
            day, month_name, year = groups
            month = _MONTH_MAP.get(month_name.lower())
            if month:
                return f"{year}-{month}-{int(day):02d}"
    return None


def extract_nationality_from_bio(bio: str | None) -> str | None:
    """Parse the opening bio sentence for a nationality adjective."""
    if not bio:
        return None
    m = _BIO_NATIONALITY_RE.search(bio)
    if not m:
        return None
    nat = _STRIP_PREFIXES.sub("", m.group(1).strip()).lower()
    # Validate against known list to avoid false positives
    if nat in _KNOWN_NATIONALITIES:
        return nat.title()
    # Accept multi-word if any word matches known list (e.g. "Cape Verdean")
    parts = nat.split()
    for part in parts:
        if part in _KNOWN_NATIONALITIES:
            return nat.title()
    return None


def parse_squads(cur):
    cur.execute("TRUNCATE staging.player_squad_stints")
    cur.execute("""
        SELECT payload
        FROM raw.wiki_player_pages
        WHERE kind = 'squad_table'
        ORDER BY scraped_at DESC
    """)
    count = 0
    for (payload,) in cur.fetchall():
        season = payload.get("season") or "current"
        club = payload.get("club_title") or ""
        team_id = payload.get("team_id")
        url = payload.get("source_url") or ""
        if not team_id:
            continue
        for player in payload.get("players") or []:
            name = clean_name(player.get("name"))
            if not is_person_name(name):
                continue
            cur.execute(
                """INSERT INTO staging.player_squad_stints
                   (player_name, wiki_title, team_id, club_raw, season, position, shirt_no,
                    appearances, goals, source_url)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (player_name, team_id, season) DO UPDATE SET
                     appearances = COALESCE(EXCLUDED.appearances, staging.player_squad_stints.appearances),
                     goals = COALESCE(EXCLUDED.goals, staging.player_squad_stints.goals),
                     wiki_title = COALESCE(EXCLUDED.wiki_title, staging.player_squad_stints.wiki_title)""",
                (
                    name,
                    clean_name(player.get("wiki_title")) or name,
                    team_id,
                    club,
                    season,
                    player.get("position"),
                    player.get("shirt_no"),
                    player.get("appearances"),
                    player.get("goals"),
                    url,
                ),
            )
            if season != "current" and player.get("appearances") is not None:
                cur.execute(
                    """INSERT INTO staging.player_season_stats
                       (player_name, season, club_raw, stat_type, stat_value, source_url)
                       VALUES (%s,%s,%s,%s,%s,%s)
                       ON CONFLICT DO NOTHING""",
                    (name, season, club, "appearances", player.get("appearances"), url),
                )
            if season != "current" and player.get("goals") is not None:
                cur.execute(
                    """INSERT INTO staging.player_season_stats
                       (player_name, season, club_raw, stat_type, stat_value, source_url)
                       VALUES (%s,%s,%s,%s,%s,%s)
                       ON CONFLICT DO NOTHING""",
                    (name, season, club, "goals", player.get("goals"), url),
                )
            count += 1
    print(f"squad stints: {count}")


def ensure_stubs(cur):
    cur.execute(
        """
        SELECT DISTINCT ON (lower(wiki_title))
            player_name, wiki_title, position, club_raw, season, source_url
        FROM staging.player_squad_stints
        ORDER BY lower(wiki_title), CASE WHEN season = 'current' THEN 0 ELSE 1 END
        """
    )
    added = 0
    for name, title, position, club, season, url in cur.fetchall():
        name = clean_name(name)
        title = clean_name(title) or name
        if not is_person_name(name):
            continue
        pid = player_id(title or name, None)
        cur.execute(
            "SELECT 1 FROM staging.players WHERE player_id = %s OR lower(full_name) = lower(%s)",
            (pid, name),
        )
        if cur.fetchone():
            continue
        current_club = club if season == "current" else None
        cur.execute(
            """INSERT INTO staging.players
               (player_id, wiki_title, full_name, position, current_club, source_url)
               VALUES (%s,%s,%s,%s,%s,%s)
               ON CONFLICT (player_id) DO NOTHING""",
            (pid, title or name, name, position, current_club, url),
        )
        added += 1
    print(f"stub profiles: {added}")


def parse_profiles(cur):
    cur.execute("TRUNCATE staging.players, staging.player_career, staging.player_injuries")
    cur.execute("""
        SELECT DISTINCT ON (payload->>'wiki_title') payload
        FROM raw.wiki_player_pages
        WHERE kind = 'player_profile'
        ORDER BY payload->>'wiki_title', scraped_at DESC
    """)
    players = 0
    for (payload,) in cur.fetchall():
        title = clean_name(payload.get("wiki_title"))
        if not is_person_name(title):
            continue
        pid = player_id(title, payload.get("wikidata_id"))
        info = payload.get("infobox") or {}
        bio = payload.get("bio") or ""

        # Nationality: prefer infobox, fall back to bio sentence extraction.
        nationality = (
            pick(info, "nationality", "national team")
            or extract_nationality_from_bio(bio)
        )

        # DOB: prefer infobox field, fall back to bio text extraction.
        raw_dob = pick(info, "date of birth") or extract_dob_from_bio(bio)

        cur.execute(
            """INSERT INTO staging.players
               (player_id, wiki_title, full_name, date_of_birth, place_of_birth, height,
                position, current_club, nationality, wikidata_id, image_url, bio, source_url)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (player_id) DO UPDATE SET
                 full_name    = EXCLUDED.full_name,
                 date_of_birth = COALESCE(EXCLUDED.date_of_birth,
                                          staging.players.date_of_birth),
                 place_of_birth = COALESCE(EXCLUDED.place_of_birth,
                                           staging.players.place_of_birth),
                 height       = COALESCE(EXCLUDED.height, staging.players.height),
                 position     = COALESCE(EXCLUDED.position, staging.players.position),
                 current_club = COALESCE(EXCLUDED.current_club, staging.players.current_club),
                 nationality  = COALESCE(EXCLUDED.nationality, staging.players.nationality),
                 wikidata_id  = COALESCE(EXCLUDED.wikidata_id, staging.players.wikidata_id),
                 image_url    = COALESCE(EXCLUDED.image_url, staging.players.image_url),
                 bio          = COALESCE(EXCLUDED.bio, staging.players.bio),
                 source_url   = EXCLUDED.source_url""",
            (
                pid,
                title,
                clean_name(pick(info, "full name", "name") or title),
                raw_dob,
                pick(info, "place of birth"),
                pick(info, "height"),
                pick(info, "position", "position(s)"),
                clean_name(pick(info, "current team", "club")),
                nationality,
                payload.get("wikidata_id"),
                payload.get("image_url"),
                bio,
                payload.get("source_url"),
            ),
        )
        players += 1
        for stint in payload.get("career") or []:
            club = clean_name(stint.get("club"))
            years = (stint.get("years") or "").strip()
            if not club or not years:
                continue
            cur.execute(
                """INSERT INTO staging.player_career
                   (player_id, years, club_raw, appearances, goals, source_url)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT DO NOTHING""",
                (pid, years, club, stint.get("appearances"), stint.get("goals"), payload.get("source_url")),
            )
        for detail in payload.get("injuries") or []:
            cur.execute(
                """INSERT INTO staging.player_injuries (player_id, detail, source_url)
                   VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",
                (pid, detail, payload.get("source_url")),
            )
    print(f"profiles: {players}")


def parse_leaderboards(cur):
    # Do not truncate: load_season_player_stats.py owns multi-league rows.
    cur.execute("""
        SELECT DISTINCT ON (season, table_index) season, section, rows, source_url
        FROM raw.wiki_tables
        ORDER BY season, table_index, scraped_at DESC
    """)
    count = 0
    for season, section, rows, url in cur.fetchall():
        key = STAT_SECTIONS.get((section or "").strip().lower())
        if not key or not rows:
            continue
        body = rows[1:] if isinstance(rows, list) else json.loads(rows)[1:]
        for row in body:
            name, club, value = _leaderboard_row(row)
            if not name or value is None:
                continue
            cur.execute(
                """INSERT INTO staging.player_season_stats
                   (player_name, season, club_raw, stat_type, stat_value, source_url)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT DO NOTHING""",
                (name, season, club or "", key, value, url),
            )
            count += 1
    print(f"leaderboard stats: {count}")


def _leaderboard_row(row: list) -> tuple[str | None, str | None, int | None]:
    cells = [str(c).strip() for c in row if str(c).strip()]
    if len(cells) < 2:
        return None, None, None
    name = None
    club = None
    value = None
    for cell in cells:
        if re.fullmatch(r"\d+", cell):
            if value is None and name:
                value = int(cell)
            continue
        if name is None:
            name = re.sub(r"\[.*?\]", "", cell).strip()
        elif club is None and not re.fullmatch(r"\d+", cell):
            club = cell
        else:
            value = as_int(cell) or value
    if value is None:
        value = as_int(cells[-1])
    return name, club, value


def main():
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        parse_profiles(cur)
        parse_leaderboards(cur)
        parse_squads(cur)
        ensure_stubs(cur)


if __name__ == "__main__":
    main()
