# Choosing Storage: Files, Postgres, DuckDB, and When You Actually Need a Warehouse

The storage question arrives early and is usually answered by habit. A team that knows PostgreSQL puts everything in PostgreSQL. A team that has used a cloud warehouse reaches for one again. Neither choice is examined, because storage feels like plumbing rather than design. Then the pipeline grows, and the consequences appear: queries that scan far more data than they need, a monthly bill that nobody can explain, or a database that cannot be reproduced on a laptop.

While building a data platform that collects statistics from public sources, I had to make this decision twice. Once for the raw layer, where collected data lands untouched, and once for the modelled layer, where transformed tables are queried. The two layers wanted different answers, and treating them as one decision would have been a mistake.

This article compares the main storage options for analytical data pipelines and explains how to choose between them. It covers files in object storage, PostgreSQL, DuckDB, and cloud warehouses, along with the file formats that sit underneath several of them.

The rule that should guide the choice fits in six words: **separate the landing zone from serving.**

Storage matters because it sets the limits on cost, portability, and how easily someone else can run your project. It is also the decision that is hardest to reverse quietly, since everything else reads from it.

This article covers three decisions. The first is **how to store raw data**, where durability and portability matter most. The second is **where to put modelled data**, where query patterns and concurrency decide the answer. The third is **when to move to a warehouse**, which is a question of scale, governance, and organisation rather than of technology alone.

If your storage decision was made by habit, the raw layer is the best place to re-examine it.

## Store raw data as portable files

The first decision concerns the landing zone. The claim is that raw data should be stored as plain files in a documented layout, not loaded directly into a database.

### Why files rather than tables

Raw data has different requirements from modelled data. It is written once, read occasionally, and never updated. Its structure often changes as sources change, which makes a fixed table schema an obstacle rather than a help. It also has to survive long enough to reprocess when a parser turns out to be wrong.

Files meet all of these requirements. In the sports platform, each collection run writes a JSON Lines file, where every line is one captured block of a page, and the files are organised in a directory layout that records the partition keys.

```
data/raw/source=wikipedia_season/league=RSA_PREM/season=2025-26/run=<timestamp>.jsonl
```

This is Hive-style partitioning, a convention in which each directory level records a key and its value. It is read natively by query engines and by cloud storage tools, which means the same layout works on a laptop today and in object storage later without code changes.

The practical benefit shows up the first time you query the raw layer without loading it anywhere. An analytical engine can read the directory structure as columns.

```sql
-- DuckDB reading the raw layer directly, treating directories as columns
select league, season, count(*) as blocks
from read_json_auto('data/raw/**/*.jsonl', hive_partitioning = true)
where source = 'wikipedia_season'
group by league, season
order by season;
```

The same query works unchanged against files on object storage once the path is replaced with a bucket address, which is what makes the layout worth choosing before you need it.


### Choosing a format

The format choice is usually between a row-based text format and a columnar binary format.

| Format | Strengths | Weaknesses |
|---|---|---|
| JSON Lines | Human-readable, tolerant of changing structure, easy to append | Larger files, slower to query |
| Parquet | Compact, fast columnar reads, typed | Requires a schema, less convenient for irregular data |
| CSV | Universally supported | No types, poor with nested or irregular data |

The platform uses JSON Lines for raw data because captured pages are irregular and a readable format makes debugging far easier. Published outputs use Parquet, where the data is regular, the schema is stable, and compact fast reads matter.

### Qualifiers and objections

A common objection is that files without a database mean no indexes and no constraints. That is true, and it is the point. The raw layer is not there to be queried efficiently. It is there to be a durable record of what a source said at a moment in time, and structure is imposed later, where it can be changed without losing anything.

Once raw data is safe, the modelled layer can be optimised for reading.

## Match modelled storage to your query pattern

The second decision concerns the database that holds transformed tables. The claim is that the right choice depends on how the data is queried and by how many people, not on how much data there is.

### The realistic options at small and medium scale

**PostgreSQL** is a general-purpose relational database that handles concurrent readers and writers, enforces constraints, and is available everywhere. It is row-based, which suits lookups and moderate aggregation, and it is not designed for scanning very large tables column by column.

**DuckDB** is an in-process analytical database. It runs inside your application with no server to operate, uses a columnar engine built for aggregation, and reads Parquet, CSV, and JSON directly, including files in object storage. It reached version 1.0 in 2024 and is now used inside a range of analytics and business intelligence tools. It is not a multi-user server, and it does not provide user management or row-level security as database features.

**A cloud warehouse** such as BigQuery, Snowflake, or Redshift provides scale, concurrency, and governance as managed services, in exchange for cost and a dependency on a vendor.

### How the sports platform chose

The platform's modelled data is queried by dbt during builds, by a dashboard, and occasionally by me. It is measured in millions of rows rather than billions, and several processes write to it concurrently. That pattern fits PostgreSQL, which also gives constraints and foreign keys that catch modelling mistakes early.

Those constraints are worth writing out, because they turn a class of modelling error into an immediate failure rather than a wrong number in a report.

```sql
-- sql/init/003_core_schema.sql  (simplified)
CREATE TABLE IF NOT EXISTS core.match (
    match_id      TEXT PRIMARY KEY,
    season_id     TEXT NOT NULL,
    match_date    DATE,                       -- null until result is confirmed
    home_team_id  TEXT,                       -- null until team resolves via alias
    away_team_id  TEXT,
    home_goals    SMALLINT,
    away_goals    SMALLINT,
    source_id     TEXT NOT NULL
);
```

The table allows nullable team ids and dates because a match row can arrive before its team aliases are resolved. The constraints that matter — teams must differ, goals must be non-negative, team ids must be present in the final output — are enforced by dbt tests rather than by the database itself. That keeps the raw load fast and puts the correctness checks where they run alongside the models they guard.

A cloud warehouse would accept all of this data without complaint, because most warehouses do not enforce foreign keys. On a small platform, dbt tests serve the same purpose.


DuckDB has a clear role in the same project, but in a different place. It is the right engine for local ad-hoc analysis where starting a server would be unnecessary friction — for example, scanning the raw JSONL files to debug a parser without loading anything into Postgres. In this project, both serving layers (Streamlit and Observable) read Postgres directly rather than a published Parquet layer.

The Parquet export pattern is worth knowing for larger projects. It would look like this:

```sql
-- example: publish one mart as Parquet for downstream readers without DB credentials
INSTALL postgres; LOAD postgres;
ATTACH 'dbname=football user=football host=localhost port=5434' AS pg (TYPE postgres);
COPY (select * from pg.mart.player_season)
  TO 'data/published/player_season.parquet' (FORMAT PARQUET);
```

Applying this pattern would let the public Observable site read files at build time rather than querying the database, which removes the need to expose Postgres credentials to the build environment.


### Qualifiers and objections

If the workload were mostly large scans by a single process, DuckDB would be the better main engine, and it would be faster. If the platform served many concurrent users with strict access controls, PostgreSQL alone would eventually be insufficient. The lesson is that these tools are complements more often than competitors.

That raises the question of when a managed warehouse becomes necessary.

## Know when a warehouse earns its cost

The third decision is about scale and organisation. The claim is that a warehouse solves problems of size, concurrency, and governance, and that adopting one before you have those problems buys complexity rather than capability.

### The signals that justify a warehouse

The first signal is data volume that a single machine can no longer handle comfortably. A single server can hold a surprising amount of data, so this arrives later than most people expect.

The second signal is concurrency. When many analysts and tools query the same data at once, a managed warehouse handles that far better than a single database instance.

The third signal is governance. Role-based access control, row-level security, and audit logs are built into warehouses and are laborious to reproduce elsewhere.

The fourth signal is organisational. When several teams need to share data on common terms, a warehouse provides a natural meeting point.

### Keep the migration path open

Whatever you choose now, a few habits make a later move cheaper. Keep raw data in open formats and partitioned layouts, so it can be read by any engine. Write transformations in standard SQL where possible, and keep vendor-specific functions to a minimum. Store configuration such as connection details outside the code. Finally, make sure the whole platform can be started locally, which keeps development independent of a paid service.

### Qualifiers and objections

The opposite mistake also exists. A team that stays on a single machine for too long ends up hand-building queuing, access control, and scaling that a warehouse would have provided. The signals above are worth reviewing on a schedule rather than only when something breaks.

Cost comparisons also need care. A warehouse's price depends on query patterns as much as on storage, and a badly written model can cost more than the storage it reads.

## Conclusion

Storage looks like plumbing, which is why it is so often decided by habit. The decision sets your costs, your portability, and how easily anyone else can run your work.

Store raw data as portable files in a documented layout, so it can be reprocessed and read by any engine. Choose modelled storage according to how the data is queried and by whom, remembering that a server database and an in-process engine often work best together. Move to a warehouse when volume, concurrency, governance, or organisational sharing genuinely demand it, and keep your formats and SQL portable so that the move stays possible.

**Separate the landing zone from serving.**

The best storage decision is the one you can undo. Keep your raw data open and your SQL standard, and every later choice stays available to you.

As a first step, check whether your pipeline could be started from scratch on a laptop. If it could not, the reason you find will usually point directly at a storage decision worth revisiting.

*This is the tenth article in a series on data engineering lessons from building pipelines on external sources. The next article covers the serving layer, and how to choose between dashboards, applications, and static sites.*

**Tags:** Data Engineering, PostgreSQL, DuckDB, Data Architecture, Data Storage
