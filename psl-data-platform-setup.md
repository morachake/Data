# African Football Data Platform — Project Setup Guide

**Phase 1 target:** South African Premiership (PSL / Betway Premiership)
**MVP scope:** fixtures, results and standings for the last five completed seasons, validated against published totals.

---

## 1. Stack

| Layer | Tool | Why |
|---|---|---|
| Scraping | Scrapy (+ scrapy-playwright only if a site needs JavaScript) | Retries, throttling, robots.txt, caching and file export built in |
| Raw storage | Local `data/raw/` folder (swap for S3/GCS later) | Keep every scrape untouched so you can reprocess |
| Database | PostgreSQL 16 (Docker) | Simple, free, good enough for years of league data |
| Transformation | dbt (dbt-postgres) | Versioned SQL models + data tests |
| Orchestration | Dagster | Asset-based, easy local UI, schedules |
| Language | Python 3.11+ | |

---

## 2. Repository structure

```
african-football-data/
├── docker-compose.yml
├── .env
├── requirements.txt
├── README.md
├── sql/
│   └── init/
│       └── 001_raw_schema.sql
├── data/
│   └── raw/                      # untouched scraper output (git-ignored)
├── ingestion/                    # Scrapy project
│   ├── scrapy.cfg
│   └── ingestion/
│       ├── settings.py
│       └── spiders/
│           └── wiki_psl_seasons.py
├── loaders/
│   ├── load_raw.py               # JSONL -> raw.wiki_tables
│   └── parse_results_matrix.py   # raw tables -> staging.wiki_results
├── transform/                    # dbt project
│   ├── dbt_project.yml
│   ├── seeds/
│   │   ├── teams.csv
│   │   ├── team_aliases.csv
│   │   └── season_checks.csv
│   ├── models/
│   │   ├── staging/
│   │   │   ├── sources.yml
│   │   │   └── stg_wiki_results.sql
│   │   └── core/
│   │       ├── schema.yml
│   │       ├── fct_matches.sql
│   │       └── standings.sql
│   └── tests/
│       └── assert_season_totals.sql
└── orchestration/
    └── definitions.py            # Dagster assets
```

Add to `.gitignore`: `data/raw/`, `.env`, `.scrapy/`, `transform/target/`, `transform/logs/`.

---

## 3. Environment setup

```bash
mkdir african-football-data && cd african-football-data
git init
python -m venv .venv && source .venv/bin/activate
```

`requirements.txt`:

```
scrapy>=2.11
psycopg[binary]>=3.1
dbt-postgres>=1.8
dagster>=1.8
dagster-webserver>=1.8
python-dotenv>=1.0
```

```bash
pip install -r requirements.txt
```

`.env`:

```
POSTGRES_USER=football
POSTGRES_PASSWORD=football
POSTGRES_DB=football
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

---

## 4. Database (Docker)

`docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16
    env_file: .env
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./sql/init:/docker-entrypoint-initdb.d
volumes:
  pgdata:
```

`sql/init/001_raw_schema.sql` (runs automatically on first start):

```sql
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;

-- Every table scraped from a Wikipedia season page, stored as-is
CREATE TABLE IF NOT EXISTS raw.wiki_tables (
    id           BIGSERIAL PRIMARY KEY,
    source       TEXT        NOT NULL,
    source_url   TEXT        NOT NULL,
    season       TEXT        NOT NULL,
    table_index  INT         NOT NULL,
    section      TEXT,
    rows         JSONB       NOT NULL,
    scraped_at   TIMESTAMPTZ NOT NULL,
    loaded_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Match results parsed out of the season results matrix
CREATE TABLE IF NOT EXISTS staging.wiki_results (
    season        TEXT NOT NULL,
    home_team_raw TEXT NOT NULL,
    away_team_raw TEXT NOT NULL,
    home_goals    INT  NOT NULL,
    away_goals    INT  NOT NULL,
    source_url    TEXT NOT NULL,
    PRIMARY KEY (season, home_team_raw, away_team_raw)
);
```

```bash
docker compose up -d
```

> Note: the core tables (teams, aliases, matches, standings) are built by dbt, not by hand-written DDL. That keeps all business logic versioned in one place.

---

## 5. Scrapy project

```bash
scrapy startproject ingestion
```

### 5.1 Settings — `ingestion/ingestion/settings.py`

Replace/add these values (be a polite scraper):

```python
BOT_NAME = "ingestion"
SPIDER_MODULES = ["ingestion.spiders"]
NEWSPIDER_MODULE = "ingestion.spiders"

# Identify yourself with a way to contact you
USER_AGENT = "AfricanFootballData/0.1 (+https://github.com/<you>/african-football-data; <your-email>)"

ROBOTSTXT_OBEY = True
DOWNLOAD_DELAY = 1.0
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
CONCURRENT_REQUESTS_PER_DOMAIN = 2

# Cache pages during development so you don't re-hit sites while debugging
HTTPCACHE_ENABLED = True
HTTPCACHE_EXPIRATION_SECS = 86400

# Every run lands as a new timestamped JSONL file in the raw layer
FEEDS = {
    "../data/raw/%(name)s/%(time)s.jsonl": {"format": "jsonlines", "encoding": "utf8"},
}
FEED_EXPORT_ENCODING = "utf-8"
```

### 5.2 First spider — `ingestion/ingestion/spiders/wiki_psl_seasons.py`

Scrapes every `wikitable` on each season page and stores the rows raw. Parsing happens later, so a Wikipedia layout change never loses data.

```python
from datetime import datetime, timezone
from urllib.parse import quote

import scrapy

SEASONS = ["2021–22", "2022–23", "2023–24", "2024–25", "2025–26"]  # en dash, as in Wikipedia titles


class WikiPslSeasonsSpider(scrapy.Spider):
    name = "wiki_psl_seasons"
    allowed_domains = ["en.wikipedia.org"]

    def start_requests(self):
        for season in SEASONS:
            title = f"{season} South African Premiership".replace(" ", "_")
            url = f"https://en.wikipedia.org/wiki/{quote(title)}"
            yield scrapy.Request(url, callback=self.parse_season, cb_kwargs={"season": season})

    def parse_season(self, response, season):
        scraped_at = datetime.now(timezone.utc).isoformat()
        for i, table in enumerate(response.css("table.wikitable")):
            rows = []
            for tr in table.css("tr"):
                cells = [
                    " ".join(t.strip() for t in cell.css("::text").getall() if t.strip())
                    for cell in tr.css("th, td")
                ]
                if cells:
                    rows.append(cells)

            section = " ".join(
                table.xpath("preceding::*[self::h2 or self::h3][1]//text()").getall()
            ).strip()

            yield {
                "source": "wikipedia",
                "source_url": response.url,
                "season": season,
                "table_index": i,
                "section": section,
                "rows": rows,
                "scraped_at": scraped_at,
            }
```

Run it:

```bash
cd ingestion
scrapy crawl wiki_psl_seasons
cd ..
```

Check `data/raw/wiki_psl_seasons/` for the output file.

### 5.3 When Scrapy alone is not enough

If a source loads its data with JavaScript (you'll see empty tables in `scrapy shell <url>`):

1. First, open the browser dev tools Network tab. Many sites load data from a JSON endpoint you can request directly with Scrapy — faster and more reliable than rendering.
2. If there is no usable endpoint, install `scrapy-playwright` and enable it only for that spider.

Always check each site's terms of service and robots.txt before adding it as a source. Prefer official sources (psl.co.za) and openly licensed ones (Wikipedia).

---

## 6. Loaders

### 6.1 `loaders/load_raw.py` — JSONL into Postgres

```python
import json
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()
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
                (item["source"], item["source_url"], item["season"], item["table_index"],
                 item["section"], json.dumps(item["rows"]), item["scraped_at"]),
            )
            count += 1
    return count


if __name__ == "__main__":
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "data/raw/wiki_psl_seasons")
    latest = max(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    print(f"Loaded {load_file(latest)} tables from {latest}")
```

### 6.2 `loaders/parse_results_matrix.py` — find and unpivot the results grid

Wikipedia season pages include a home/away results matrix: row *i* is the home team, column *j* is the away team, and columns follow the same order as rows. This script finds that table and turns it into one row per match.

```python
import os
import re

import psycopg
from dotenv import load_dotenv

load_dotenv()
DSN = (
    f"host={os.environ['POSTGRES_HOST']} port={os.environ['POSTGRES_PORT']} "
    f"dbname={os.environ['POSTGRES_DB']} user={os.environ['POSTGRES_USER']} "
    f"password={os.environ['POSTGRES_PASSWORD']}"
)
SCORE = re.compile(r"^(\d+)\s*[–-]\s*(\d+)$")
FOOTNOTE = re.compile(r"\[.*?\]")


def clean(cell: str) -> str:
    return FOOTNOTE.sub("", cell).strip()


def is_results_matrix(rows) -> bool:
    if len(rows) < 11:
        return False
    header, body = rows[0], rows[1:]
    n = len(body)
    if len(header) - 1 != n:
        return False
    scores = sum(1 for r in body for c in r[1:] if SCORE.match(clean(c)))
    return scores >= 0.8 * n * (n - 1)


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
            if season not in found and is_results_matrix(rows):
                found[season] = (rows, url)

        for season, (rows, url) in found.items():
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
```

If a season prints fewer matches than expected, inspect that season's tables in `raw.wiki_tables` — some pages split results by round or use a different layout. Handle it as a special case rather than weakening the general parser.

---

## 7. dbt project

```bash
dbt init transform   # choose postgres, then edit ~/.dbt/profiles.yml as below
```

`~/.dbt/profiles.yml`:

```yaml
transform:
  target: dev
  outputs:
    dev:
      type: postgres
      host: localhost
      port: 5432
      user: football
      password: football
      dbname: football
      schema: core
      threads: 4
```

### 7.1 Seeds — the entity-resolution layer

`seeds/teams.csv` — one row per real club, with a stable ID you control:

```csv
team_id,team_name,country
RSA_ORLANDO_PIRATES,Orlando Pirates,South Africa
RSA_MAMELODI_SUNDOWNS,Mamelodi Sundowns,South Africa
RSA_KAIZER_CHIEFS,Kaizer Chiefs,South Africa
```

`seeds/team_aliases.csv` — every spelling seen in any source, mapped to a team_id:

```csv
alias,source,team_id
Orlando Pirates,wikipedia,RSA_ORLANDO_PIRATES
Mamelodi Sundowns,wikipedia,RSA_MAMELODI_SUNDOWNS
Kaizer Chiefs,wikipedia,RSA_KAIZER_CHIEFS
```

Fill these in from the distinct names in `staging.wiki_results`:

```sql
SELECT DISTINCT home_team_raw FROM staging.wiki_results ORDER BY 1;
```

`seeds/season_checks.csv` — published totals to validate against (fill from each season's summary):

```csv
season,expected_matches,expected_goals
2025–26,240,485
```

### 7.2 Models

`models/staging/sources.yml`:

```yaml
version: 2
sources:
  - name: staging
    schema: staging
    tables:
      - name: wiki_results
```

`models/staging/stg_wiki_results.sql`:

```sql
select
    season,
    trim(home_team_raw) as home_team_raw,
    trim(away_team_raw) as away_team_raw,
    home_goals,
    away_goals,
    source_url
from {{ source('staging', 'wiki_results') }}
```

`models/core/fct_matches.sql`:

```sql
with r as (select * from {{ ref('stg_wiki_results') }}),
a as (select * from {{ ref('team_aliases') }} where source = 'wikipedia')

select
    md5(r.season || ha.team_id || aa.team_id) as match_id,
    r.season,
    ha.team_id as home_team_id,
    aa.team_id as away_team_id,
    r.home_goals,
    r.away_goals,
    case when r.home_goals > r.away_goals then 'H'
         when r.home_goals < r.away_goals then 'A'
         else 'D' end as result,
    'wikipedia' as source,
    r.source_url
from r
left join a ha on ha.alias = r.home_team_raw
left join a aa on aa.alias = r.away_team_raw
```

`models/core/standings.sql`:

```sql
with m as (select * from {{ ref('fct_matches') }}),
rows as (
    select season, home_team_id as team_id, home_goals as gf, away_goals as ga,
           case result when 'H' then 3 when 'D' then 1 else 0 end as pts,
           (result = 'H')::int as w, (result = 'D')::int as d, (result = 'A')::int as l
    from m
    union all
    select season, away_team_id, away_goals, home_goals,
           case result when 'A' then 3 when 'D' then 1 else 0 end,
           (result = 'A')::int, (result = 'D')::int, (result = 'H')::int
    from m
)
select
    season, team_id,
    count(*) as played, sum(w) as won, sum(d) as drawn, sum(l) as lost,
    sum(gf) as goals_for, sum(ga) as goals_against, sum(gf) - sum(ga) as goal_diff,
    sum(pts) as points,
    rank() over (partition by season order by sum(pts) desc, sum(gf) - sum(ga) desc, sum(gf) desc) as position
from rows
group by season, team_id
```

> Points deductions and tie-break rules vary by season. When your standings disagree with the official table, that's usually the reason — record deductions in a seed and apply them here.

### 7.3 Tests

`models/core/schema.yml`:

```yaml
version: 2
models:
  - name: fct_matches
    columns:
      - name: match_id
        tests: [unique, not_null]
      - name: home_team_id
        tests:
          - not_null   # fails if a new team spelling isn't in team_aliases yet
          - relationships: {to: ref('teams'), field: team_id}
      - name: away_team_id
        tests:
          - not_null
          - relationships: {to: ref('teams'), field: team_id}
```

`tests/assert_season_totals.sql` — fails if match counts or goal totals don't match published figures:

```sql
with actual as (
    select season, count(*) as matches, sum(home_goals + away_goals) as goals
    from {{ ref('fct_matches') }}
    group by season
)
select c.season, c.expected_matches, a.matches, c.expected_goals, a.goals
from {{ ref('season_checks') }} c
left join actual a using (season)
where a.matches is distinct from c.expected_matches
   or a.goals   is distinct from c.expected_goals
```

Run everything:

```bash
cd transform
dbt seed && dbt build
```

The `not_null` test on team IDs is your early-warning system: whenever a source introduces a new spelling (renamed, promoted or sold clubs), the build fails until you add the alias.

---

## 8. Orchestration — `orchestration/definitions.py`

```python
import subprocess
from pathlib import Path

from dagster import Definitions, ScheduleDefinition, asset, define_asset_job

ROOT = Path(__file__).resolve().parents[1]


def run(cmd, cwd=ROOT):
    subprocess.run(cmd, cwd=cwd, check=True)


@asset
def wiki_raw_scrape():
    run(["scrapy", "crawl", "wiki_psl_seasons"], cwd=ROOT / "ingestion")


@asset(deps=[wiki_raw_scrape])
def wiki_raw_loaded():
    run(["python", "loaders/load_raw.py"])


@asset(deps=[wiki_raw_loaded])
def wiki_results_staged():
    run(["python", "loaders/parse_results_matrix.py"])


@asset(deps=[wiki_results_staged])
def dbt_core_models():
    run(["dbt", "seed"], cwd=ROOT / "transform")
    run(["dbt", "build"], cwd=ROOT / "transform")


pipeline = define_asset_job("psl_pipeline", selection="*")

defs = Definitions(
    assets=[wiki_raw_scrape, wiki_raw_loaded, wiki_results_staged, dbt_core_models],
    jobs=[pipeline],
    schedules=[ScheduleDefinition(job=pipeline, cron_schedule="0 6 * * 1")],  # Mondays 06:00
)
```

```bash
dagster dev -f orchestration/definitions.py
```

Open http://localhost:3000 and materialize all assets. Later, swap the shell calls for `dagster-dbt` for per-model lineage.

---

## 9. Milestone checklist

**Week 1 — foundations**
- [ ] Repo, Docker Postgres and virtualenv running
- [ ] Wikipedia spider scraping 5 seasons into `data/raw/`
- [ ] Raw tables loaded into `raw.wiki_tables`

**Week 2 — clean data**
- [ ] Results matrix parsed for all 5 seasons
- [ ] `teams.csv` and `team_aliases.csv` complete
- [ ] `fct_matches` and `standings` building; all tests green
- [ ] Final standings match the official tables for every season

**Week 3 — second source + publish**
- [ ] Spider for psl.co.za (current season results)
- [ ] Reconciliation model: flag matches where the two sources disagree
- [ ] Export `fct_matches` and `standings` to CSV/Parquet in the repo
- [ ] README: sources, pipeline diagram, known data issues
- [ ] Short write-up on LinkedIn / X

**Next phases**
- Goalscorers, cards and lineups → `players` + `player_aliases` (same pattern as teams)
- Expand to Egypt and Morocco, then Kenya, Nigeria, Ghana, Tanzania
- Public API (FastAPI) and a simple website

---

## 10. Principles to keep

1. **Raw is sacred.** Never edit raw files; fix problems in parsing or transformation.
2. **Every row knows its source.** Keep `source` and `source_url` all the way through.
3. **Stable IDs you own.** Never use a source's name or ID as your primary key.
4. **Validate against published facts.** Match counts, goal totals and final tables are free tests.
5. **One league done completely beats ten done badly.**
6. **Scrape politely.** Obey robots.txt, identify yourself, throttle, cache, respect terms of service.
