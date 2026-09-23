# Build for the Sources You Have: Designing Source-Agnostic Pipelines

A sixteen-team sports league plays 240 matches in a season, so five seasons contain 1,200 matches. When I planned to collect detailed player statistics for such a league through a commercial sports data API, its free tier allowed 100 requests per day, and the statistics required one request per match. Collecting five seasons for a single league would have taken twelve days, and the platform I was building was meant to cover more than a dozen leagues.

A better source existed, but it was not a source I could build on yet. What I had were public websites and open archives. A paid API would have to wait until the project had shown that it was worth paying for.

If you build on data you do not control, you may face the same situation. The sources available today may be scraped, partial, or unstable, while the ideal source, such as a paid API, a vendor feed, or a formal data partnership, lies somewhere in the future. This article describes an architecture for building a proper warehouse on the sources you have without locking yourself into them.

The idea behind the design fits in four words: **keep source details upstream.**

It matters because both obvious alternatives are traps. If a pipeline is designed around one source, that source's assumptions leak into every model, and replacing it later means rewriting the warehouse. If you wait for the ideal source, you may never build anything at all.

This article presents three design decisions. The first is to **isolate volatility at the edge**, so that changes in sources stay close to where they happen. The second is to **own your identifiers**, so that no source's names or IDs become the keys of your warehouse. The third is to **grow by configuration**, so that new datasets and new sources are added without writing new pipelines.

If you are building on imperfect sources today and hoping for better ones tomorrow, these decisions turn tomorrow's upgrade into a small change instead of a rebuild. We will start at the edge.

## Isolate volatility at the edge

The first decision concerns where change is allowed to travel. The claim is that the parts of a pipeline that deal with unstable sources should be small, simple, and separate from the parts that interpret data.

### The layers

The sports platform follows a layered design in which data moves from its raw form, through cleaned models that no longer depend on any source, to tables built for analysis.

| Layer | Tool | Responsibility |
|---|---|---|
| Configuration | YAML files | Define which leagues exist and which sources cover them |
| Ingestion | Scrapy | Fetch pages and capture their structure |
| Raw | JSON Lines files | Keep every collected item as it arrived |
| Parsing | Python | Turn captured structure into typed rows |
| Staging | PostgreSQL | Hold typed rows that are still specific to each source |
| Core | dbt | Hold one clean model that does not depend on any source |
| Marts | dbt | Hold metrics and tables built for analysis |
| Orchestration | Dagster | Schedule and run the pipeline by partition |

The same layering works with other tools. An API-based pipeline might replace Scrapy with a small Python client, and a cloud warehouse might replace PostgreSQL. What matters is where each responsibility sits.

### Collectors capture structure, parsers own meaning

The most important boundary in the design sits between ingestion and parsing. The collectors, which are written with Scrapy, are deliberately simple. Each one fetches a page, finds the blocks of interest such as tables, and records their structure, including rows, cells, links, and the nearest heading. A collector never decides what a cell means, and it never calculates anything.

```python
# ingestion/ingestion/spiders/  (pattern — simplified)
def parse(self, response):
    for index, table in enumerate(response.css("table")):
        yield {
            "source_id": self.source_id,
            "league_id": self.league_id,
            "season": self.season,
            "url": response.url,
            "block_type": "table",
            "block_index": index,
            "payload": self.capture_rows(table),   # cell text exactly as captured
            "fetched_at": self.fetched_at,
        }
```

Parsers then read these blocks and decide what they mean. A parser decides that a table is a grid of results, that a particular cell contains a score, and that a row belongs to a particular team.

The reason for this split is that the layout of a source usually changes far more often than the meaning of the data inside it. When a layout changes, only the collector or parser for that source needs attention, and nothing downstream is affected. API integrations benefit from the same split. A client that stores raw responses and a separate parser that interprets them can absorb an API version change in one place.

### Store raw data in a portable layout

The platform writes raw data as JSON Lines files organised in Hive-style partitions. Hive-style partitioning is a folder naming convention in which each folder level records a key and its value.

```
data/raw/source=wikipedia_season/league=RSA_PREM/season=2025-26/run=<timestamp>.jsonl
```

These files currently live on a local disk. Because the layout follows a widely supported convention, the same structure can move to cloud object storage such as Amazon S3 without changes to the code that reads it, and query engines such as DuckDB and Spark can read it directly.

### Qualifiers and objections

Separating collectors from parsers means writing two pieces of code where one might seem sufficient. For a script that runs only once, that separation is unnecessary. For a pipeline expected to survive years of changes in its sources, it keeps each change contained to a single place.

With change contained at the edge, the next task is preventing source-specific details from spreading inward.

## Own your identifiers

The second decision concerns keys. The claim is that a warehouse which uses a source's identifiers as its own keys is permanently tied to that source.

### Staging keeps source detail, and core removes it

The staging layer stores data in a form that is still specific to each source. A staging row records which source it came from, which page or response produced it, and which run collected it. Names and identifiers appear exactly as the source provided them.

The core layer, which is built with dbt, is where source-specific details are resolved. Every entity receives an internal identifier that the platform owns. Names and identifiers from each source are mapped to those internal identifiers through alias tables, using the entity resolution process described in the second article of this series. Disagreements between sources are settled at the same stage, and the result is a single model of the business entities and events the platform cares about.

### The boundary rule

One rule protects this boundary: no model downstream of the core layer may depend on which source a value came from in order to work. Source information is still carried forward for auditing, but no calculation, join, or filter relies on it.

The core model is the last place where source-specific values appear, and they appear only as inputs to the alias join or as audit columns.

```sql
-- transform/models/core/match.sql  (simplified)
select
    md5(r.league_id || '_' || r.season || '_'
        || ha.team_id || '_' || aa.team_id)       as match_id,
    r.match_date,
    ha.team_id                                    as home_team_id,
    aa.team_id                                    as away_team_id,
    r.home_goals,
    r.away_goals,
    r.source_id,                                  -- carried for auditing only
    r.source_url                                  -- carried for auditing only
from {{ ref('stg_match') }} r
join {{ ref('team_alias') }} ha on ha.alias = r.home_team_raw and ha.source_id = r.source_id
join {{ ref('team_alias') }} aa on aa.alias = r.away_team_raw and aa.source_id = r.source_id
```

A useful way to test the rule is to search the models built on top of this one for the string `source_id`. If it appears anywhere except in an audit column or a lineage view, the boundary has been crossed.


This rule is what makes a warehouse ready for better data. If the warehouse used one source's names or IDs as its keys, adding a new source would mean changing the keys of every table. Because internal identifiers form the contract, a new source only needs its values mapped to identifiers that already exist.

The same principle appears in many businesses. A company that keys its customer tables on the IDs from one CRM system faces a painful migration when it changes CRM. A company that keys them on its own customer IDs only needs to map the new system's IDs.

### Qualifiers and objections

Owning identifiers requires work. Alias tables must be maintained, and some matches need human review. When every source shares a reliable global identifier, such as a tax registration number or a product barcode, using it directly is simpler and entirely reasonable. The public sources in the sports platform did not share any such identifier, so the platform had to create its own.

Contained edges and owned identifiers make a warehouse stable. The final decision makes it easy to extend.

## Grow by configuration

The third decision concerns expansion. The claim is that adding a new dataset or a new source should require a configuration change, not a new pipeline.

### Datasets and sources as configuration

The sports platform starts from two configuration files. One describes each dataset, including its region, language, season format, and the sources that cover it. The other describes each source, including its licence, whether it is allowed, and its priority when sources disagree.

```yaml
# config/leagues.yml
leagues:
  - league_id: RSA_PREM
    name: South African Premier Division
    region: Southern Africa
    language: en
    season_format: aug_may
    sources: [wikipedia_season, rsssf_tables]
    seasons: ["2022-23", "2023-24", "2024-25"]
```

A retail company could use the same structure to describe each store system or regional feed, and a logistics company could use it to describe each carrier integration.

### Partitions generated from configuration

Dagster, the orchestration tool used in the platform, runs the pipeline as assets partitioned by league and season, and it builds both dimensions from `config/leagues.yml`. Each partition can be run, retried, or backfilled independently. A five-season backfill for one league does not block the weekly update of another, and when a new league is added to the configuration its partitions appear automatically.

The link between the configuration file and the orchestrator lives in `orchestration/definitions.py`, and it is the reason a new league requires no new pipeline code.

```python
# orchestration/definitions.py  (simplified)
import yaml
from dagster import MultiPartitionsDefinition, StaticPartitionsDefinition, asset

with open("config/leagues.yml") as f:
    cfg = yaml.safe_load(f)

_league_ids = sorted({lg["league_id"] for lg in cfg["leagues"] if lg.get("seasons")})
_seasons    = sorted({s for lg in cfg["leagues"] for s in lg.get("seasons", [])})

multi_partition = MultiPartitionsDefinition({
    "league_id": StaticPartitionsDefinition(_league_ids),
    "season":    StaticPartitionsDefinition(_seasons),
})

@asset(partitions_def=multi_partition)
def wikipedia_season_raw(context):
    league_id = context.partition_key.keys_by_dimension["league_id"]
    season    = context.partition_key.keys_by_dimension["season"]
    # ... run scrapy crawl for this (league_id, season) pair
```

Everything downstream, including schedules, retries, and backfills, then operates on those partitions without knowing anything about the leagues themselves.


### The upgrade path

This is where the API from the introduction returns. When the platform is ready for a paid source, adding it will require one new entry in the source configuration, a loader that writes to the existing staging tables, and a higher priority than the existing sources. The reconciliation rules will then prefer the new source automatically. Coverage will improve, while the core models, marts, and dashboards remain unchanged.

Deferring the paid dependency was not a rejection of it. It was a decision to keep that future choice inexpensive.

### Qualifiers and objections

Configuration-driven pipelines can become a maze of YAML when logic moves into configuration files. The rule followed in the sports platform is that configuration describes what varies between datasets and sources, such as names, formats, and priorities, while logic stays in code, where it can be reviewed and tested.

## Conclusion

A twelve-day backfill for a single dataset was the constraint that shaped this design. It meant building on the available sources first, and it meant building in a way that would not need to be undone when better sources arrived.

The architecture rests on three decisions. It isolates volatility at the edge, with simple collectors, separate parsers, and a portable raw layout. It owns its identifiers, so that the core model never depends on any source's names or keys. It grows by configuration, so that new datasets and sources become additions rather than rewrites.

**Keep source details upstream.**

The sources you start with are rarely the sources you finish with. An architecture that accepts this allows you to begin today with what you have, instead of waiting for what you want.

As a first step, search your transformation models for any join or filter that uses a source system's name or identifier directly. Each one you find marks a place where changing that source would mean changing your warehouse.

*This is the fourth article in a series on data engineering lessons from building pipelines on external sources. The next article covers data products that show users how complete their data is, instead of hiding it.*

**Tags:** Data Engineering, Data Architecture, dbt, Dagster, Data Pipelines
