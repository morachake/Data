"""
Dagster asset definitions.

Partitioning
------------
Assets that are partitioned use a MultiPartitionsDefinition keyed by
(league_id, season).  The partition keys are generated from config/leagues.yml
so adding a new league with seasons automatically creates new Dagster partitions.

Backward compatibility
----------------------
The original flat psl_pipeline job is kept as an alias so any existing
schedules or manual triggers that reference it by name still work.
New code should use the partitioned assets and ``psl_pipeline_partitioned``.
"""

import subprocess
from pathlib import Path

import yaml
from dagster import (
    Definitions,
    MultiPartitionsDefinition,
    MultiPartitionKey,
    ScheduleDefinition,
    StaticPartitionsDefinition,
    asset,
    define_asset_job,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"


# ---------------------------------------------------------------------------
# Partition definitions — built from leagues.yml
# ---------------------------------------------------------------------------

def _load_leagues() -> dict:
    with open(CONFIG_DIR / "leagues.yml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_partitions() -> tuple[list[str], list[str]]:
    """Return (league_ids_with_seasons, all_seasons_across_leagues)."""
    cfg = _load_leagues()
    league_ids = sorted(
        {lg["league_id"] for lg in cfg["leagues"] if lg.get("seasons")}
    )
    seasons = sorted(
        {s for lg in cfg["leagues"] for s in lg.get("seasons", [])}
    )
    return league_ids, seasons


_league_ids, _seasons = _build_partitions()

league_partition = StaticPartitionsDefinition(_league_ids)
season_partition = StaticPartitionsDefinition(_seasons)

multi_partition = MultiPartitionsDefinition(
    {"league_id": league_partition, "season": season_partition}
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(cmd, cwd=ROOT, **kwargs):
    subprocess.run(cmd, cwd=cwd, check=True, **kwargs)


# ---------------------------------------------------------------------------
# Non-partitioned assets (legacy, RSA Wikipedia pipeline)
# ---------------------------------------------------------------------------

@asset(description="Scrape Wikipedia PSL season pages into data/raw/")
def wiki_raw_scrape():
    run(["scrapy", "crawl", "wiki_psl_seasons"], cwd=ROOT / "ingestion")


@asset(deps=[wiki_raw_scrape], description="Load raw JSONL into raw.wiki_tables")
def wiki_raw_loaded():
    run(["python", "loaders/load_raw.py"])


@asset(deps=[wiki_raw_loaded], description="Unpivot results matrices into staging.wiki_results")
def wiki_results_staged():
    run(["python", "loaders/parse_results_matrix.py"])


@asset(deps=[wiki_results_staged], description="Scrape player profiles for PSL clubs")
def wiki_players_scraped():
    run(["scrapy", "crawl", "wiki_psl_players"], cwd=ROOT / "ingestion")


@asset(deps=[wiki_players_scraped], description="Load player JSONL into raw.wiki_player_pages")
def wiki_players_loaded():
    run(["python", "loaders/load_players.py"])


@asset(deps=[wiki_players_loaded], description="Parse player data into staging tables")
def wiki_players_staged():
    run(["python", "loaders/parse_players.py"])


@asset(
    deps=[wiki_results_staged, wiki_players_staged],
    description="Run dbt seeds + build to produce core and player models",
)
def dbt_core_models():
    run(["dbt", "seed", "--profiles-dir", "."], cwd=ROOT / "transform")
    run(["dbt", "build", "--profiles-dir", ".", "--no-partial-parse"], cwd=ROOT / "transform")


# ---------------------------------------------------------------------------
# Partitioned assets (new architecture — Phase 1+)
# ---------------------------------------------------------------------------

@asset(
    partitions_def=multi_partition,
    description="Scrape one league × season partition from Wikipedia",
)
def wikipedia_season_raw(context):
    key: MultiPartitionKey = context.partition_key
    league_id = key.keys_by_dimension["league_id"]
    season = key.keys_by_dimension["season"]

    # Verify this league actually covers this season before crawling.
    cfg = _load_leagues()
    league = next((lg for lg in cfg["leagues"] if lg["league_id"] == league_id), None)
    if league is None or season not in league.get("seasons", []):
        context.log.info(
            "Partition %s/%s not active — skipping", league_id, season
        )
        return

    run(
        [
            "scrapy", "crawl", "wiki_psl_seasons",
            "-a", f"league_id={league_id}",
            "-a", f"season={season}",
            "-s", "HTTPCACHE_ENABLED=False",   # always fetch fresh in scheduled runs
        ],
        cwd=ROOT / "ingestion",
    )


@asset(
    partitions_def=multi_partition,
    deps=[wikipedia_season_raw],
    description="Run dbt for one league × season after its raw data is loaded",
)
def dbt_partition_build(context):
    key: MultiPartitionKey = context.partition_key
    league_id = key.keys_by_dimension["league_id"]
    season = key.keys_by_dimension["season"]

    # Guard: only build if this (league, season) is actually active.
    # The MultiPartitionsDefinition is the cross-product of all league_ids × all
    # seasons across every league; many combinations don't exist in leagues.yml.
    cfg = _load_leagues()
    league = next((lg for lg in cfg["leagues"] if lg["league_id"] == league_id), None)
    if league is None or season not in league.get("seasons", []):
        context.log.info(
            "Partition %s/%s not active in leagues.yml — skipping dbt build",
            league_id, season,
        )
        return

    run(
        [
            "dbt", "build",
            "--profiles-dir", ".",
            "--select", "tag:partitioned",
            "--vars", f'{{"league_id": "{league_id}", "season": "{season}"}}',
            "--no-partial-parse",   # always re-parse so config changes take effect immediately
        ],
        cwd=ROOT / "transform",
    )


# ---------------------------------------------------------------------------
# Jobs and schedules
# ---------------------------------------------------------------------------

# Legacy flat job — non-partitioned assets only.
# The partitioned assets (wikipedia_season_raw, dbt_partition_build) are
# excluded here; run them via psl_pipeline_partitioned instead.
pipeline = define_asset_job(
    "psl_pipeline",
    selection=[
        wiki_raw_scrape,
        wiki_raw_loaded,
        wiki_results_staged,
        wiki_players_scraped,
        wiki_players_loaded,
        wiki_players_staged,
        dbt_core_models,
    ],
)

# Partitioned job — run all active partitions.
psl_pipeline_partitioned = define_asset_job(
    "psl_pipeline_partitioned",
    selection=[wikipedia_season_raw, dbt_partition_build],
)

defs = Definitions(
    assets=[
        # Legacy
        wiki_raw_scrape,
        wiki_raw_loaded,
        wiki_results_staged,
        wiki_players_scraped,
        wiki_players_loaded,
        wiki_players_staged,
        dbt_core_models,
        # Partitioned
        wikipedia_season_raw,
        dbt_partition_build,
    ],
    jobs=[pipeline, psl_pipeline_partitioned],
    schedules=[
        # Current-season weekly refresh — Mondays 06:00 EAT (UTC+3 = 03:00 UTC)
        ScheduleDefinition(
            job=psl_pipeline_partitioned,
            cron_schedule="0 3 * * 1",
            name="weekly_current_season",
        ),
        # Legacy schedule kept for backward compat
        ScheduleDefinition(
            job=pipeline,
            cron_schedule="0 6 * * 1",
            name="legacy_psl_pipeline",
        ),
    ],
)
