import re
from urllib.parse import unquote, urljoin

INJURY_RE = re.compile(
    r"([^.]*\b(?:injur(?:y|ed|ies)|ACL|hamstring|fracture|sidelined|out for)\b[^.]*\.)",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"^\d{4}")
SKIP_TITLES = ("File:", "Category:", "Template:", "Help:", "Wikipedia:", "Special:", "Talk:")
WIKI_PREFIXES = (
    "https://en.wikipedia.org/wiki/",
    "http://en.wikipedia.org/wiki/",
    "/wiki/",
)
NON_PLAYER_SNIPPETS = (
    "association football",
    "football association",
    "national football team",
    "premier soccer",
    "premiership",
    "premier division",
)
NON_PLAYER_TITLES = {
    "Midfielder",
    "Forward",
    "Defender",
    "Goalkeeper",
    "Captain (association football)",
    "Loan (sports)",
    "Substitute (association football)",
}


def wiki_title_from_href(href: str | None) -> str | None:
    if not href:
        return None
    path = None
    for prefix in WIKI_PREFIXES:
        if href.startswith(prefix):
            path = href[len(prefix) :]
            break
    if path is None:
        return None
    title = unquote(path.split("#", 1)[0].split("?", 1)[0].replace("_", " "))
    if title.startswith(SKIP_TITLES):
        return None
    return title


def is_likely_player_title(title: str | None) -> bool:
    if not title or title.startswith("List of "):
        return False
    if title in NON_PLAYER_TITLES:
        return False
    low = title.lower()
    if any(snippet in low for snippet in NON_PLAYER_SNIPPETS):
        return False
    if title.endswith(" F.C.") or title.endswith(" A.F.C.") or title.endswith(" S.C."):
        return False
    if " season" in low:
        return False
    return True


def player_column_index(header: list[str]) -> int | None:
    for i, cell in enumerate(header):
        token = re.sub(r"\s+", " ", cell).strip().lower()
        if token in {"player", "name", "player name"}:
            return i
    return None


def position_column_index(header: list[str]) -> int | None:
    for i, cell in enumerate(header):
        token = re.sub(r"\s+", " ", cell).strip().lower()
        if token in {"pos", "pos.", "position", "position(s)"}:
            return i
    return None


def looks_like_footballer(info: dict, bio: str, career: list) -> bool:
    if career:
        return True
    keys = " ".join(info.keys()).lower()
    if any(token in keys for token in ("position", "senior career", "current team", "date of birth")):
        return True
    text = (bio or "").lower()
    return "footballer" in text or "soccer player" in text or "football player" in text


def cell_text(cell) -> str:
    return " ".join(t.strip() for t in cell.css("::text").getall() if t.strip())


def infobox_map(response) -> dict[str, str]:
    data = {}
    for row in response.css("table.infobox tr"):
        header = cell_text(row.css("th"))
        value = cell_text(row.css("td"))
        if header and value:
            data[header.lower()] = value
    return data


def infobox_image(response) -> str | None:
    src = response.css("meta[property='og:image']::attr(content)").get()
    if not src:
        src = response.css("table.infobox img::attr(src)").get()
    if not src:
        return None
    if src.startswith("//"):
        return "https:" + src
    return src


def first_bio(response) -> str:
    paras = []
    for p in response.css("div.mw-parser-output p"):
        text = re.sub(r"\s+", " ", " ".join(p.css("::text").getall())).strip()
        if len(text) > 60:
            paras.append(text)
        if len(paras) == 2:
            break
    return " ".join(paras)


def wikidata_id(response) -> str | None:
    href = response.css("li#t-wikibase a::attr(href)").get() or ""
    if "/wiki/Q" in href:
        return href.rsplit("/", 1)[-1]
    return None


def career_rows(response) -> list[dict]:
    rows = []
    for row in response.css("table.infobox tr"):
        cells = [cell_text(c) for c in row.css("th, td")]
        if len(cells) < 3 or not YEAR_RE.match(cells[0]):
            continue
        years, club, *rest = cells
        apps = _to_int(rest[0]) if rest else None
        goals = _to_int(rest[1].strip("()")) if len(rest) > 1 else None
        rows.append({"years": years, "club": club, "appearances": apps, "goals": goals})
    return rows


def appearance_table_rows(table) -> list[list[str]]:
    return [[cell_text(c) for c in tr.css("th, td")] for tr in table.css("tr")]


def looks_like_apps_table(header: list[str]) -> bool:
    joined = " ".join(header).lower()
    has_player = player_column_index(header) is not None or "player" in joined
    has_apps = any(token in joined for token in ("apps", "app", "appearances", "caps"))
    has_goals = "goal" in joined or "gls" in joined
    return has_player and has_apps and has_goals


def looks_like_squad_table(header: list[str]) -> bool:
    if header and len(header[0]) > 80:
        return False
    if player_column_index(header) is None:
        return False
    joined = " ".join(header).lower()
    return "pos" in joined or "position" in joined or looks_like_apps_table(header)


def extract_squad_players(table, header: list[str], rows: list[list[str]]) -> list[dict]:
    idx = player_column_index(header)
    pos_idx = position_column_index(header)
    if idx is None:
        return []
    players = []
    seen = set()
    body_rows = rows[1:]
    body_trs = table.css("tr")[1:]
    for row, tr in zip(body_rows, body_trs):
        if idx >= len(row):
            continue
        raw_name = re.sub(r"\([^)]*\)", "", row[idx]).strip()
        name = re.sub(r"\[\s*\d+\s*\]", "", raw_name)
        name = re.sub(r"\s+", " ", name).strip(" -–—")
        if not name or name.lower() in {"player", "name", "total"}:
            continue
        if not re.search(r"[A-Za-z]{3,}", name):
            continue
        title = None
        cells = tr.css("th, td")
        if idx < len(cells):
            for href in cells[idx].css("a::attr(href)").getall():
                candidate = wiki_title_from_href(href)
                if is_likely_player_title(candidate):
                    title = candidate
                    break
        key = (title or name).lower()
        if key in seen:
            continue
        seen.add(key)
        shirt = row[0].strip() if row and re.fullmatch(r"\d+|—|-|–", row[0].strip()) else None
        position = row[pos_idx].strip() if pos_idx is not None and pos_idx < len(row) else None
        stats = _row_stats(header, row)
        players.append(
            {
                "name": name,
                "wiki_title": title or name,
                "shirt_no": shirt,
                "position": position,
                "appearances": stats.get("appearances"),
                "goals": stats.get("goals"),
            }
        )
    return players


def _row_stats(header: list[str], row: list[str]) -> dict:
    stats: dict[str, int | None] = {}
    for i, cell in enumerate(header):
        token = re.sub(r"\s+", " ", cell).strip().lower()
        if i >= len(row):
            continue
        value = _to_int(row[i])
        if value is None:
            continue
        if token in {"apps", "app", "appearances", "caps", "total", "psl", "dstv premiership", "betway premiership"}:
            stats["appearances"] = value
        if token in {"goals", "gls", "goal"}:
            stats["goals"] = value
    return stats


def extract_injuries(text: str) -> list[str]:
    seen = []
    for match in INJURY_RE.findall(text or ""):
        sentence = match.strip()
        if 40 <= len(sentence) <= 400 and sentence not in seen:
            seen.append(sentence)
        if len(seen) >= 12:
            break
    return seen


def _to_int(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^\d]", "", value)
    return int(digits) if digits else None


def absolute_url(response, href: str) -> str:
    return urljoin(response.url, href)
