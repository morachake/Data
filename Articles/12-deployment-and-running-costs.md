# Deployment and Running Costs: Keeping a Small Data Platform Cheap Without Making It Fragile

Most writing about data platforms assumes a budget. It describes managed warehouses, managed orchestration, managed transformation, and a monitoring service, and it is written for teams whose infrastructure bill is somebody else's line item. A great deal of real data engineering happens on the other side of that assumption: a side project, an internal tool, a first platform at a small company, or a product that has to prove itself before it can justify spending.

I built a data platform in that situation. It collects statistics from public sources, transforms them, and publishes a site, and it had to run at almost no cost without becoming something that only works on my laptop.

This article is about deploying and operating a small data platform. It covers local development, containers, scheduling, hosting, monitoring, and the specific trade-offs that keep costs low without making the system fragile.

The principle that guided the decisions fits in five words: **reproducible first, then cheap.**

The topic matters because cost and fragility are usually traded against each other by accident rather than on purpose. A platform that is cheap because it runs on one unmanaged machine that nobody can rebuild is not cheap. It is borrowed time.

This article covers three decisions. The first is **making the platform reproducible**, which is what makes everything else safe. The second is **choosing where each part runs**, since a small platform has genuinely different needs from a large one. The third is **operating it responsibly**, which means monitoring, backups, and knowing what would happen if it stopped.

If your platform currently exists in one place and one place only, reproducibility is where to start.

## Make the platform reproducible

The first decision is to ensure that the whole platform can be recreated from the repository. The claim is that reproducibility, not scale, is what separates a real platform from a personal setup.

### Containers for anything with state

The database is the part most likely to become unreproducible, because it accumulates state that is easy to create by hand and hard to recreate. Running it as a container with its initialisation scripts in the repository solves this.

```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: football
      POSTGRES_PASSWORD: football
      POSTGRES_DB: football
    ports:
      - "5434:5432"       # host port 5434 avoids clashing with a local Postgres
    volumes:
      - football_pgdata:/var/lib/postgresql/data
      - ./sql/init:/docker-entrypoint-initdb.d   # schemas applied automatically on first start
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U football -d football"]
volumes:
  football_pgdata:
```

Anyone who clones the repository gets the same database version, the same schemas, and the same starting structure, without following instructions in a document that is always slightly out of date.

### Pin everything you depend on

Dependencies should be pinned to specific versions, and configuration should come from environment variables rather than from values typed into a running system. Secrets belong in a local environment file that is excluded from version control, with the repository containing an example file listing the variables that are required.

### Make every step runnable from a command line

Each stage of the platform, including collection, loading, transformation, and serving, should be runnable as a single terminal command. This makes the pipeline testable, portable between orchestrators, and usable by anyone who has cloned the repository, and it prevents the platform from becoming dependent on any one runtime environment.

In this project each step is a direct command, documented in the README:

```bash
# start the database
docker compose up -d

# collect one partition
cd ingestion && scrapy crawl wiki_psl_seasons -a league_id=RSA_PREM -a season=2024-25

# load raw JSONL into staging tables
python loaders/load_raw.py

# build and test the dbt models
cd transform && dbt build --profiles-dir .

# start the internal dashboard
streamlit run serving/app.py

# build the public Observable site
cd observable && npm run build
```

Anything the orchestrator does should be one of these commands, which means the orchestrator can be replaced without touching the pipeline. A Makefile is a useful addition: this project defines these steps in the README rather than a Makefile, but either approach achieves the same goal of documenting the surface.


### Qualifiers and objections

Containers add a layer to learn, and on a personal project it can be tempting to install the database directly and move on. The cost appears later, when a version differs between machines, or when the project has to move to a server, and nobody can remember which extensions were installed by hand.

Once the platform is reproducible, where it runs becomes a straightforward cost decision.

## Choose where each part runs

The second decision is about placement. The claim is that the parts of a small platform have different requirements, and that treating them separately is what keeps the bill small.

### Four parts, four answers

**The pipeline** needs compute only while it runs. For a weekly or daily schedule, that is a small amount of time, so it can run on a modest virtual machine or in a scheduled continuous integration job rather than on a permanently running cluster.

**The database** needs to be available whenever the pipeline or the dashboard runs. A small managed database removes backup and patching work for a predictable monthly cost, while a self-managed container on the same virtual machine is cheaper and puts that work back on you.

**The internal dashboard** is used by a few people, so it can run on the same machine as the database, behind authentication, or even be started on demand rather than left running.

**The public site**, if the data updates on a schedule, can be generated as static files and hosted on a static hosting service. This is usually the cheapest and most reliable part of the whole system, because there is no server to keep running and traffic spikes are handled by the host.

### A practical arrangement for a small platform

| Part | Placement | Rough cost profile |
|---|---|---|
| Pipeline runs | Scheduled job on a small virtual machine or a CI runner | Low, proportional to run time |
| Database | Container on the same machine, or a small managed instance | The main recurring cost |
| Internal dashboard | Same machine, protected by authentication | Negligible |
| Public site | Static hosting, rebuilt when the pipeline runs | Often free at small scale |

The sports platform follows this arrangement. The pipeline and database are containers, the internal dashboard runs beside them, and the public site is generated from exported files, which keeps the public-facing part independent of the database entirely.

### Scheduled jobs as a deployment target

A continuous integration service can double as a scheduler for small workloads. A scheduled workflow can check out the repository, run the pipeline, and publish the results, which avoids maintaining a server at all. The limitations are real, including run-time limits and the need to manage secrets carefully, so this suits pipelines measured in minutes rather than hours.

The workflow is short, and the manual trigger alongside the schedule matters more than it looks, because it is what lets you rerun a failed job without waiting a week.

```yaml
# .github/workflows/weekly-pipeline.yml  (pattern — not currently in this repo)
name: weekly-pipeline
on:
  schedule:
    - cron: "0 6 * * 1"
  workflow_dispatch:

jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: |
          cd ingestion && scrapy crawl wiki_psl_seasons -s HTTPCACHE_ENABLED=False
          python loaders/load_raw.py
          cd ../transform && dbt build --profiles-dir .
          cd ../observable && npm run build && npm run deploy
        env:
          POSTGRES_HOST: ${{ secrets.POSTGRES_HOST }}
          POSTGRES_PASSWORD: ${{ secrets.POSTGRES_PASSWORD }}
```

Note that the workflow calls the same commands a developer would run locally, so there is no separate continuous integration version of the pipeline to keep in step. This project currently uses Dagster for scheduling rather than GitHub Actions, but either approach produces the same result.


### Qualifiers and objections

Self-managing a database is the decision most likely to age badly. It is cheaper in money and more expensive in attention, particularly for backups and upgrades. A reasonable compromise is to self-manage while the platform is young and to move to a managed instance as soon as anyone other than you depends on it.

Cheap infrastructure is only sustainable if you know when it fails, which is the final decision.

## Operate it responsibly

The third decision is about operations. The claim is that a small platform needs a small amount of operational discipline, and that the absence of it is what turns cheap into fragile.

### Monitor the data, not just the jobs

Job monitoring tells you whether a process exited successfully. Data monitoring tells you whether the results are usable. At a minimum, record for every run the number of items collected per partition, the number of rows loaded, the results of data tests, and the time the run finished.

A simple record is enough to start. In this project run statistics are written as JSON manifest files under `data/raw/_manifests/` by the `RunStatsPipeline` Scrapy pipeline after each crawl. A natural next step is to load those manifests into a database table and build a small dashboard on top of them:

```sql
-- aspirational: ops.run_log built from data/raw/_manifests/*.json
CREATE TABLE ops.run_log (
    run_id        UUID PRIMARY KEY,
    source_id     TEXT NOT NULL,
    league_id     TEXT NOT NULL,
    season        TEXT NOT NULL,
    started_at    TIMESTAMPTZ NOT NULL,
    finished_at   TIMESTAMPTZ,
    status        TEXT NOT NULL,
    items_total   INT,
    tests_passed  INT,
    tests_failed  INT
);
```

### Back up what cannot be regenerated

Some data can be regenerated by rerunning the pipeline, and some cannot. Raw collected files usually cannot, because the source may have changed. Manual decisions, such as reviewed entity matches and overrides, definitely cannot, because they represent human work.

Those two categories deserve real backups, tested by restoring them at least once. Everything else can be rebuilt from them.

The backup itself can be a single script, run on a schedule and retained for a fixed period.

```bash
#!/usr/bin/env bash
set -euo pipefail

stamp=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p backups

# 1. the database — user/db are 'football' as set in docker-compose.yml
docker compose exec -T postgres pg_dump -U football football \
  | gzip > "backups/db-$stamp.sql.gz"

# 2. raw collected files, which cannot be recreated if a source changes
tar -czf "backups/raw-$stamp.tar.gz" data/raw

# 3. keep one month of history
find backups -name '*.gz' -mtime +30 -delete
```

The part people skip is the restore. A backup that has never been restored is an assumption, and the cheapest time to test it is before anything has gone wrong.


### Know your failure story before you need it

Write down, in a short document, what happens if the machine disappears tomorrow. If the answer is that the repository plus the backups plus a few commands would restore the platform within an hour or two, the design is sound. If the answer is uncertain, that uncertainty is your real risk, and it is cheaper to fix while the platform is small.

### Qualifiers and objections

All of this is a small amount of work, but it is work that never feels urgent. The way I keep it honest is to treat restoration as a feature: if the platform cannot be restored, it is not finished, regardless of how well the pipeline runs today.

## Conclusion

Running cheaply is not the same as running carelessly. The difference is whether the platform exists in a repository or only on a machine.

Make the platform reproducible, with containers for stateful parts, pinned dependencies, and every step runnable from a command line. Place each part where its requirements are cheapest to meet, keeping the public layer independent of the database. Then operate it responsibly, with monitoring of the data itself, backups of what cannot be regenerated, and a documented answer to the question of what happens when the machine disappears.

**Reproducible first, then cheap.**

A platform that can be rebuilt is a platform you can afford to run anywhere. That freedom is worth more than any single hosting saving.

As a first step, try to start your platform from a fresh clone of its repository on a different machine. Whatever stops you is the most valuable item on your backlog.

*This is the twelfth article in a series on data engineering lessons from building pipelines on external sources. The series covers sourcing decisions, entity resolution, reliability, architecture, data quality, fair metrics, and the tooling choices behind each layer.*

**Tags:** Data Engineering, DevOps, Docker, Data Infrastructure, Cost Optimization
