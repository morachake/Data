# African Football Data Platform

Phase 1 covers the South African Premiership (PSL / Betway Premiership): fixtures, results, and standings from the last five completed seasons through the current season.

## Stack

- Scrapy for Wikipedia ingestion
- PostgreSQL 16 (Docker) for storage
- dbt for transforms and tests
- Dagster for orchestration
- Streamlit for exploring standings, charts and results

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
docker-compose up -d
```

Postgres is published on **5434** so it does not collide with local Homebrew Postgres.

Wait until Postgres is healthy, then run the pipeline:

```bash
# 1. Scrape Wikipedia season pages into data/raw/
cd ingestion
scrapy crawl wiki_psl_seasons
cd ..

# 2. Load raw JSONL into Postgres
python loaders/load_raw.py

# 3. Unpivot the results matrices
python loaders/parse_results_matrix.py

# 4. Build core models
cd transform
dbt seed --profiles-dir .
dbt build --profiles-dir .
cd ..
```

Or run everything from the Dagster UI:

```bash
dagster dev -f orchestration/definitions.py
```

Open http://localhost:3000 and materialize `psl_pipeline`.

To explore the loaded data:

```bash
streamlit run dashboard/app.py
```

Open http://localhost:8501. Use **League** for tables and charts, or **Players** to open a profile (photo, career apps/goals, PSL leader stats, injury notes). Players include those still in the league and those who have since left.

To refresh player profiles:

```bash
cd ingestion
scrapy crawl wiki_psl_players
cd ..
python loaders/load_players.py
python loaders/parse_players.py
cd transform
dbt build --profiles-dir .
```

## After the first scrape

1. Check distinct team names and add any missing rows to `transform/seeds/team_aliases.csv`:

```sql
SELECT DISTINCT home_team_raw FROM staging.wiki_results ORDER BY 1;
```

2. Replace `expected_goals` of `0` in `transform/seeds/season_checks.csv` with published season totals. `0` means "not filled yet" and is skipped by the totals test.

Wikipedia result matrices are incomplete in two completed seasons: `2021–22` has two unfilled date cells (238 of 240), and `2024–25` has 19 cancelled fixtures (`Canc.`), so 221 matches. `season_checks.csv` matches those scraped totals.

## Layout

```
├── docker-compose.yml
├── ingestion/          # Scrapy project
├── loaders/            # JSONL -> Postgres, results-matrix parser
├── transform/          # dbt models, seeds, tests
├── orchestration/      # Dagster assets
├── dashboard/          # Streamlit explorer
├── sql/init/           # raw + staging schemas
└── data/raw/           # untouched scraper output (git-ignored)
```
