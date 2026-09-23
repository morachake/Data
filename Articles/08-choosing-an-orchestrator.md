# Choosing an Orchestrator: Cron, Airflow, Dagster, and What You Are Really Buying

Every pipeline starts with a schedule, and every schedule starts with cron. A line in a crontab runs a script at six o'clock every Monday, and for a while that is genuinely enough. The trouble begins when the pipeline grows past one script. The second job must wait for the first, but cron knows nothing about dependencies. A run fails halfway, and nobody finds out until a report looks wrong. You need to reprocess one month of history, so you comment out lines, run them manually, and hope you remember to put them back.

I hit this point while building a data platform that collects statistics from public websites for dozens of competitions and several seasons each. The scheduling problem was easy. The dependency, retry, and backfill problems were not.

This article compares the main orchestration options for data pipelines and explains how to decide between them. It covers cron and similar schedulers, Apache Airflow, Dagster, Prefect, and the option of building the coordination yourself.

The idea that should drive the choice fits in five words: **buy dependencies, not just schedules.**

The topic matters because an orchestrator is not a luxury for large teams. It is the part of a data platform that tells you what ran, what it produced, what failed, and what needs to run again. Without it, that knowledge lives in someone's head.

This article covers three decisions. The first is **what an orchestrator should give you** beyond running things on time. The second is **how the main tools differ**, because they are built on genuinely different ideas. The third is **how to choose one and keep the decision reversible**, which matters more than usual in a consolidating market.

If your pipeline is still held together by cron and hope, the first decision is the one to make.

## Decide what you need beyond a schedule

The first decision is about requirements. The claim is that the value of an orchestrator lies in dependencies, visibility, retries, and backfills, not in starting jobs at a particular time.

### The four capabilities that matter

**Dependency resolution** means the system knows that a transformation cannot run until its inputs have been produced. A scheduler knows about time, while an orchestrator knows about order.

**Observability** means that for any run you can see what started, what succeeded, how long it took, and what it produced. This is what turns a failure from a mystery into a ticket.

**Retries and recovery** mean that a temporary failure, such as a source timing out, is retried automatically, and that a permanent failure stops the work that depends on it rather than allowing partial results to flow downstream.

**Backfills** mean you can rerun a defined slice of history, such as one dataset for one season, without disturbing anything else. In my experience this is the capability people underestimate most, and it is the one that saves the most time.

### When cron is still the right answer

If you have one script that runs on a schedule, produces one output, and fails loudly when it breaks, cron is the correct choice. Adding an orchestrator to that situation creates infrastructure without solving a problem.

A single well-written cron entry already covers more than people expect, including preventing overlapping runs and keeping logs.

```cron
# run the pipeline every Monday at 06:00, never overlapping, with output kept
0 6 * * 1 /usr/bin/flock -n /tmp/pipeline.lock /opt/pipeline/run.sh >> /var/log/pipeline.log 2>&1
```

What this line cannot express is everything that follows from having more than one job: that the second step must wait for the first, that a failure should stop what depends on it, and that you occasionally need to rerun one dataset for one past period without touching anything else.


The signal to upgrade is not the number of scripts but the number of relationships between them. Two jobs where one depends on the other, or one job that must be rerun for historical periods, is usually where cron starts costing more than it saves.

### Qualifiers and objections

A common objection is that a few dependencies can be handled with a shell script that runs steps in order. That is true, and it works until you need partial reruns, visibility, or parallelism. At that point you are writing an orchestrator without the benefit of one that has been tested by thousands of other teams.

Once you know what you need, the differences between the tools become easier to read.

## Understand how the main tools differ

The second decision is which tool fits how you think about your pipeline. The claim is that the leading tools are built on different primitives, and that the primitive matters more than the feature list.

### Three different mental models

**Apache Airflow** is task-centric. You define a directed acyclic graph of tasks and their dependencies, and Airflow tracks whether each task ran successfully. It has the largest ecosystem and the longest history in production. Airflow 3.0 reached general availability in 2025, and later releases in the 3.x line added asset-aware scheduling, asset partitioning, DAG versioning, and multi-team deployments.

**Dagster** is asset-centric. Instead of describing tasks, you describe the data assets your pipeline produces, and Dagster works out what must run to bring them up to date. Lineage and data-quality checks are part of the model rather than something you add on top. This design fits naturally with dbt, because dbt also thinks in terms of models rather than steps.

**Prefect** is function-centric. You write ordinary Python functions and add orchestration to them, which means less ceremony and a very short path from a working script to an orchestrated one.

### An important change in the market

In July 2026, Prefect announced that it was acquiring Dagster Labs, bringing the two most widely adopted alternatives to Airflow into the same company. Both products continue under their own names and licences, Dagster's open-source licence and Dagster+ remain in place, and the combined company operates under the Prefect name.

This does not change either tool technically today, but it is relevant to a long-term choice. It is a reminder to check the governance and ownership of any tool you build a platform on, and to keep your pipeline code as portable as you reasonably can.

### Why the sports platform uses Dagster

The platform's work divides naturally into leagues and seasons, and the most common operations are "bring this season up to date" and "reprocess these five seasons for one league". Dagster's partitions express that directly: each asset is partitioned by `league_id` and `season`, and both dimensions are generated from `config/leagues.yml`.

```python
# orchestration/definitions.py  (simplified)
from dagster import asset, MultiPartitionsDefinition, MultiPartitionKey

@asset(partitions_def=multi_partition,
       description="Scrape one league × season partition from Wikipedia")
def wikipedia_season_raw(context):
    key: MultiPartitionKey = context.partition_key
    league_id = key.keys_by_dimension["league_id"]
    season    = key.keys_by_dimension["season"]
    run(["scrapy", "crawl", "wiki_psl_seasons",
         "-a", f"league_id={league_id}",
         "-a", f"season={season}",
         "-s", "HTTPCACHE_ENABLED=False"])
```

Airflow would have done the same work. Dagster's asset model simply matched the way the problem was already described, which reduced the amount of translation between the design and the code.

Dependencies are declared alongside the assets. Each asset calls a subprocess command — the same command a developer would run from a terminal — so the orchestrator can be replaced without rewriting the logic.

```python
@asset(partitions_def=multi_partition, deps=[wikipedia_season_raw],
       description="Run dbt for one league × season after its raw data is loaded")
def dbt_partition_build(context):
    key: MultiPartitionKey = context.partition_key
    league_id = key.keys_by_dimension["league_id"]
    season    = key.keys_by_dimension["season"]
    run(["dbt", "build",
         "--select", "tag:partitioned",
         "--vars", f'{{"league_id": "{league_id}", "season": "{season}"}}'])
```

The dependency ensures that a failed collection never produces a confident but incomplete dbt build for the same partition. Retry behaviour for temporary network failures is left to Scrapy's own retry settings rather than to Dagster, keeping the two concerns separate.


### Qualifiers and objections

Airflow's ecosystem advantage is real, and in an organisation that already runs Airflow, adding another orchestrator is usually the wrong move. Prefect's lighter model is a better fit for teams that want orchestration without redesigning their code around a new abstraction. None of these tools is a bad choice. They are simply optimised for different shapes of work.

Choosing well is easier if you also plan for changing your mind.

## Choose one, and keep the decision reversible

The third decision is about limiting the cost of being wrong. The claim is that orchestration should coordinate your pipeline without absorbing it.

### Keep logic out of the orchestrator

The most effective way to stay portable is to keep business logic in plain modules and let the orchestrator call them. In the sports platform, each asset is a thin wrapper that calls a function which would work identically from a command line.

Anything that can be run with a single command can be scheduled by any orchestrator. Anything expressed only as operator configuration has to be rewritten if you migrate.

### Prefer configuration you own

Partitions, schedules, and dataset lists come from configuration files in the repository rather than from definitions typed into a user interface. That makes the pipeline reviewable in version control and portable between tools.

### Start with the smallest deployment that works

For a single-node platform, running the orchestrator locally or in a small container alongside the database is enough. Managed services from the vendors remove operational work and are worth their price when a team depends on the platform, but they are not required to get the benefits described in this article.

### Qualifiers and objections

Keeping logic outside the orchestrator means giving up some of its convenience features, such as rich operators for specific systems. That is a genuine trade. In my view, the ability to run any step as a plain command, in a terminal or a test, is worth more than the convenience.

## Conclusion

Cron answers the question of when something should run. Everything else that a growing pipeline needs, such as order, visibility, recovery, and the ability to reprocess history, has to come from somewhere, and writing it yourself is a larger project than it first appears.

Choose an orchestrator by deciding what you need beyond a schedule, by matching the tool's primitive to the way you describe your pipeline, and by keeping your logic portable so the decision stays reversible in a market that is visibly consolidating.

**Buy dependencies, not just schedules.**

The orchestrator you choose will shape how you think about your data for years. Choose the one whose mental model already matches yours, and keep enough distance to change your mind later.

As a first step, write down the last three times you had to rerun part of your pipeline by hand. If any of them took more than a few minutes, backfills are the capability you are missing.

*This is the eighth article in a series on data engineering lessons from building pipelines on external sources. The next article compares transformation tools and the modelling decisions behind them.*

**Tags:** Data Engineering, Orchestration, Dagster, Apache Airflow, Data Pipelines
