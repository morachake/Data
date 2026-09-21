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
def wiki_players_scraped():
    run(["scrapy", "crawl", "wiki_psl_players"], cwd=ROOT / "ingestion")


@asset(deps=[wiki_players_scraped])
def wiki_players_loaded():
    run(["python", "loaders/load_players.py"])


@asset(deps=[wiki_players_loaded])
def wiki_players_staged():
    run(["python", "loaders/parse_players.py"])


@asset(deps=[wiki_results_staged, wiki_players_staged])
def dbt_core_models():
    run(["dbt", "seed", "--profiles-dir", "."], cwd=ROOT / "transform")
    run(["dbt", "build", "--profiles-dir", "."], cwd=ROOT / "transform")


pipeline = define_asset_job("psl_pipeline", selection="*")

defs = Definitions(
    assets=[
        wiki_raw_scrape,
        wiki_raw_loaded,
        wiki_results_staged,
        wiki_players_scraped,
        wiki_players_loaded,
        wiki_players_staged,
        dbt_core_models,
    ],
    jobs=[pipeline],
    schedules=[ScheduleDefinition(job=pipeline, cron_schedule="0 6 * * 1")],  # Mondays 06:00
)
