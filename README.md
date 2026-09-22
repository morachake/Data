# African Football Data Platform

A continental football data pipeline covering the South African Premiership and Wave 1 African leagues (Egypt, Morocco, Tanzania, Kenya, CAF Champions League). Produces a talent-scouting shortlist dashboard backed by Wikipedia + RSSSF match data.

## Stack

| Layer | Tool |
|---|---|
| Ingestion | Scrapy + `RegistrySpider` base class |
| Config | `config/leagues.yml` + `config/sources.yml` |
| Storage | PostgreSQL 16 (Docker, port **5434**) |
| Parsing | `parsers/` Python layer |
| Transform | dbt (staging → core → mart) |
| Orchestration | Dagster (league × season partitions) |
| Dashboard (Streamlit) | `serving/app.py` |
| Dashboard (Observable) | `observable/` — static, Plot-based |
| Entity resolution | `entity_resolution/` (rapidfuzz) |

---

## Prerequisites

- Python ≥ 3.11
- Docker Desktop (or any Docker daemon)
- ~500 MB disk for the database + raw data

---

## 1 — Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> **Optional:** if you later need to scrape a JavaScript-rendered source (e.g. PSL official after ToS approval), install Playwright:
> ```bash
> pip install scrapy-playwright && playwright install chromium
> ```

---

## 2 — Start Postgres

```bash
docker-compose up -d
```

Postgres is published on **5434** (not 5432) to avoid colliding with a local install.  
Wait until it is healthy (≈ 10 s), then verify:

```bash
docker-compose ps          # status should be "healthy"
```

The `sql/init/` scripts run automatically on first start and create all schemas:

| File | Creates |
|---|---|
| `001_raw_schema.sql` | `raw.*`, `staging.*` (legacy tables) |
| `002_players.sql` | `raw.wiki_player_pages`, `staging.players`, etc. |
| `003_core_schema.sql` | `core.*` entity tables + new staging tables |
| `004_entity_resolution.sql` | `staging.review_queue`, `core.player_alias` |
| `005_mart_schema.sql` | `mart` schema (shortlist, talent_score, …) |

If you need to re-run the init scripts against an existing container (e.g. after adding a new `sql/init/*.sql`):

```bash
docker-compose down -v && docker-compose up -d
```

---

## 3 — Run the full pipeline (one-shot)

### Option A — Dagster UI (recommended)

```bash
dagster dev -f orchestration/definitions.py
```

Open **http://localhost:3000**, then:
1. Click **Asset catalog** → select all assets → **Materialize selected**  
   *or* choose **Jobs → psl_pipeline → Launch run* for the legacy flat run.
2. For the new partitioned pipeline, go to **Jobs → psl_pipeline_partitioned** and launch with the desired league × season partition key.

### Option B — Manual step-by-step

```bash
# ── Scrape ────────────────────────────────────────────────────────────
# Wikipedia season pages (all active leagues from leagues.yml)
cd ingestion
scrapy crawl wiki_psl_seasons
cd ..

# RSSSF cross-check (South Africa only for now)
cd ingestion
scrapy crawl rsssf_tables -a league_id=RSA_PREM
cd ..

# Player profiles (RSA clubs only)
cd ingestion
scrapy crawl wiki_psl_players
cd ..

# ── Load raw data ──────────────────────────────────────────────────────
python loaders/load_raw.py               # raw.wiki_tables
python loaders/parse_results_matrix.py  # staging.wiki_results
python loaders/load_players.py          # raw.wiki_player_pages
python loaders/parse_players.py         # staging.players + career tables

# ── Transform ──────────────────────────────────────────────────────────
cd transform
dbt seed --profiles-dir .               # load seeds/team.csv, team_alias.csv, etc.
dbt build --profiles-dir .              # staging → core → mart
cd ..
```

### Option C — Single league × season partition

Useful when you only want to refresh one partition:

```bash
cd ingestion
scrapy crawl wiki_psl_seasons -a league_id=RSA_PREM -a season=2025-26 -s HTTPCACHE_ENABLED=False
cd ..
cd transform
dbt build --profiles-dir . --select tag:partitioned \
  --vars '{"league_id": "RSA_PREM", "season": "2025-26"}'
cd ..
```

---

## 4 — Open the dashboard

### Option A — Streamlit (original)

```bash
streamlit run serving/app.py
```

Open **http://localhost:8501**.

### Option B — Observable Framework (static, Plot-based)

> Requires Node ≥ 18 and Docker Postgres running (`docker-compose up -d`).

```bash
cd observable
npm install          # first time only
npm run dev          # starts preview server
```

Open **http://127.0.0.1:3000** — five pages auto-update as you edit source files:

| Page | URL |
|---|---|
| Overview (KPIs + coverage) | `/` |
| Leagues (standings + charts + matches) | `/league` |
| Scout Shortlist (filtered scatter + table) | `/shortlist` |
| Player Profiles | `/players` |
| Data Coverage | `/coverage` |

To build a static site for self-hosting:

```bash
npm run build    # outputs to observable/dist/
```

> **Note:** data loaders query Postgres at preview/build time. They use the same `.env` credentials as the Python stack (`POSTGRES_HOST=127.0.0.1`, `POSTGRES_PORT=5434`). If the DB is empty, pages show a "run dbt build" message instead of crashing.

| Tab | What it shows |
|---|---|
| **League** | Standings, points chart, attack/defence chart, match list |
| **Players** | Wikipedia player profiles: photo, career, PSL stats, injuries |
| **Shortlist** | Scout shortlist — filter by position, age, minutes, league, tier, score. Download as Parquet. |
| **Coverage** | Data quality tier (A/B/C) per league × season; source conflict log |

> The original `dashboard/app.py` still works for the legacy RSA-only view.

---

## 5 — Weekly refresh (automated)

A Dagster schedule (`weekly_current_season`) runs every Monday at 06:00 EAT (03:00 UTC):

```bash
# Start the Dagster daemon to activate schedules
dagster-daemon run &
dagster dev -f orchestration/definitions.py
```

---

## 6 — Adding a new season

1. Open `config/leagues.yml`, find the league entry, append the new season label to `seasons:`:

   ```yaml
   seasons:
     - "2025-26"
     - "2026-27"   # ← add this
   ```

2. Run the pipeline for that partition (Option C above).

---

## 7 — Adding a new league (Wave 1 → Wave 2/3)

1. In `config/leagues.yml`, find the stub entry for the league and populate `seasons:`, `expected_teams:`, and `season_format:`.
2. Create a source audit CSV at `docs/source_audit/<LEAGUE_ID>.csv` (copy from `docs/source_audit/RSA_PREM.csv`).
3. Add team entries to `transform/seeds/team.csv` and aliases to `transform/seeds/team_alias.csv`.
4. Run `dbt seed` then the full partition pipeline.

---

## 8 — Enabling the PSL official spider (Phase 2)

The PSL official spider is gated behind `allowed: false` in `config/sources.yml`. Before enabling:

1. Confirm your use case qualifies as non-commercial / educational under the PSL Terms (see `notes.md`).
2. Complete the source audit in `docs/source_audit/RSA_PREM.csv`.
3. Flip the flag:

   ```yaml
   # config/sources.yml
   - source_id: psl_official
     allowed: true   # ← change from false
   ```

4. Run the spider:

   ```bash
   cd ingestion && scrapy crawl psl_official
   ```

---

## 9 — Entity resolution (Phase 2)

After scraping lineups, resolve player identities across sources:

```python
import psycopg, os
from entity_resolution.player_matcher import PlayerMatcher

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    matcher = PlayerMatcher(conn)
    matcher.resolve_season("RSA_PREM", "2025-26")
```

Review grey-zone matches manually:

```bash
python -m entity_resolution.review_queue --limit 50
```

---

## 10 — Quality tests

```bash
cd transform
dbt test --profiles-dir .          # run all 11 tests (6 error + 5 warn)
dbt test --profiles-dir . --select tag:partitioned
```

Error-level tests fail the build; warn-level tests log but continue.

---

## Environment variables

The `.env` file (already committed with development defaults) is read by all Python scripts:

```
POSTGRES_USER=football
POSTGRES_PASSWORD=football
POSTGRES_DB=football
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5434
```

Change these before deploying to a shared or production environment.

---

## Project layout

```
├── config/
│   ├── leagues.yml          # league registry (17 leagues, 0–3 wave)
│   └── sources.yml          # source registry (4 sources, allowed flags)
│
├── docs/source_audit/       # per-league robots.txt + ToS audit CSVs
│
├── ingestion/               # Scrapy project
│   └── ingestion/
│       ├── items.py         # RawPageItem definition
│       ├── registry.py      # loads leagues.yml + sources.yml
│       ├── pipelines.py     # Validate → HiveWriter → RunStats
│       └── spiders/
│           ├── base.py              # RegistrySpider base class
│           ├── wiki_psl_seasons.py  # Wikipedia season pages
│           ├── wiki_psl_players.py  # Wikipedia player profiles
│           ├── rsssf_tables.py      # RSSSF plain-text results
│           └── psl_official.py      # PSL Match Centre (gated)
│
├── parsers/                 # source → StagingRow converters
│   ├── common/
│   │   ├── text.py          # footnote stripping, dash normalisation
│   │   ├── names.py         # Arabic / French name normalisation
│   │   └── dates.py         # multilingual date parsing
│   ├── wikipedia_season.py
│   ├── rsssf_tables.py
│   └── psl_official.py
│
├── entity_resolution/       # player identity matching
│   ├── name_normalise.py
│   ├── player_matcher.py    # block → score (rapidfuzz) → decide
│   └── review_queue.py      # CLI for manual review
│
├── loaders/                 # legacy JSONL → Postgres loaders
│   ├── load_raw.py          # handles both flat and Hive paths
│   ├── parse_results_matrix.py
│   ├── load_players.py
│   └── parse_players.py
│
├── sql/init/                # idempotent schema DDL
│   ├── 001_raw_schema.sql
│   ├── 002_players.sql
│   ├── 003_core_schema.sql   # core + new staging tables
│   └── 004_entity_resolution.sql
│
├── transform/               # dbt project
│   ├── models/
│   │   ├── staging/         # views over raw staging tables
│   │   ├── core/            # competition, season, team, player, match…
│   │   └── mart/            # player_season, gk_season, talent_score, shortlist…
│   ├── seeds/
│   │   ├── team.csv
│   │   ├── team_alias.csv
│   │   ├── overrides.csv
│   │   └── talent_weights.csv
│   └── tests/               # 6 error + 5 warn singular tests
│
├── orchestration/
│   └── definitions.py       # Dagster: league × season MultiPartitions
│
├── serving/                 # Streamlit dashboard (Phase 4)
│   ├── app.py               # League / Players / Shortlist / Coverage tabs
│   ├── db.py                # DB query helpers
│   └── filter_funnel.py     # shortlist empty-state diagnostics
│
├── dashboard/               # Legacy Streamlit (RSA-only, still works)
│
├── data/raw/                # Hive-partitioned JSONL (git-ignored)
│   ├── source=wikipedia_season/
│   │   └── league=RSA_PREM/
│   │       └── season=2025-26/
│   │           └── run=<timestamp>_<id>.jsonl
│   └── _manifests/          # run manifests (items, errors, duration)
│
├── docker-compose.yml
├── requirements.txt
└── .env                     # dev DB credentials (do not commit secrets)
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `RuntimeError: Source 'psl_official' is not allowed` | Spider is gated — see §8 above |
| `FileNotFoundError: config/leagues.yml` | Run commands from the repo root, not from a subdirectory |
| `No JSONL files found` | Run the scraper first (`scrapy crawl wiki_psl_seasons`) |
| dbt `Relation not found` on `stg_match` | Run `docker-compose down -v && docker-compose up -d` to re-run SQL init scripts |
| `rapidfuzz` import error | `pip install rapidfuzz>=3` |
| Wikipedia season page returns 404 | Season not yet published — normal for future seasons in `leagues.yml` |
| Dagster partitions list is empty | `config/leagues.yml` has `seasons: []` for that league — add season labels |
