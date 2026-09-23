# Choosing a Transformation Layer: SQL Scripts, dbt, SQLMesh, and the Cost of Convenience

Transformation usually begins as a folder of SQL files. Someone writes a query that cleans a table, someone else writes one that joins two cleaned tables, and a third person writes the query that feeds the dashboard. The queries work. The problem is that nothing records which one must run first, nothing tests the results, and nothing tells you which downstream tables a change will affect. The knowledge lives with whoever wrote the files.

I faced that choice while building a data platform that combines statistics from several public sources. The transformation layer had to resolve identifiers, reconcile disagreements between sources, calculate metrics, and prove that its results were correct. A folder of scripts could have produced the same tables, but it could not have proved anything.

This article compares the main ways to build a transformation layer and explains how to choose between them. It covers hand-written SQL, dbt, SQLMesh, and transformation written in Python, and it discusses what the recent consolidation in this part of the market means for that choice.

The principle behind the choice fits in five words: **transformations are code, not queries.**

This matters because the transformation layer is where raw data becomes the numbers people act on. If that logic cannot be reviewed, tested, and traced, then neither can the numbers.

This article covers three decisions. The first is **what a transformation framework actually gives you** compared with plain SQL. The second is **how the leading tools compare**, including where each one is strongest. The third is **how to protect yourself from lock-in**, which has become a live question after recent mergers.

If your transformation logic currently lives in a folder of files that only one person fully understands, the first decision is the important one.

## Understand what a framework buys you

The first decision is whether to adopt a framework at all. The claim is that a transformation framework provides four things that hand-written SQL does not, and that all four matter as soon as more than one person depends on the output.

### Dependency graphs

In a framework such as dbt, one model refers to another through a reference function rather than a hard-coded table name. The tool reads those references and builds the dependency graph automatically, so it knows the order in which models must run and which models are affected by a change.

```sql
-- transform/models/staging/stg_match.sql  (simplified)
select
    source_id,
    league_id,
    source_url,
    nullif(trim(home_team_raw), '')  as home_team_raw,
    nullif(trim(away_team_raw), '')  as away_team_raw,
    -- the en-dash normalisation lives one layer up in core/match.sql
    home_goals,
    away_goals,
    match_date,
    loaded_at
from {{ source('staging', 'stg_match') }}
```

Every model downstream refers to this one by name rather than by table, so the tool can work out both the run order and the impact of any change to it.

### Tests that live beside the models

Frameworks let you declare expectations about the data in the same repository as the transformations, so they are reviewed together and run together.

```yaml
# transform/models/core/schema.yml
- name: match
  columns:
    - name: match_id
      tests: [unique, not_null]
    - name: home_team_id
      tests:
        - not_null
        - relationships:
            to: ref('team')
            field: team_id
```

### Environments and reproducibility

The same models can run against a development schema and a production schema, driven by configuration rather than by editing the SQL. That makes it safe to try a change without touching the tables people use.

### Documentation and lineage

Because the tool knows the graph, it can generate documentation that shows where each column comes from. This is the difference between a colleague asking you how a number is calculated and a colleague looking it up.

### Qualifiers and objections

None of this is free. A framework adds a build step, a project structure, and a set of conventions to learn. For a single analysis that will never run again, plain SQL in a notebook is the right tool, and a framework is overhead. The moment the output is used by someone else, or must be produced repeatedly, the balance changes.

With the value clear, the next question is which framework to use.

## Compare the leading options honestly

The second decision is which tool to adopt. The claim is that the main options are more similar in capability than in philosophy, and that the differences worth weighing are about state, cost control, and governance.

### The main options

**dbt** is the most widely adopted SQL transformation framework, and it has the largest ecosystem of packages, integrations, and available expertise. In June 2026, Fivetran and dbt Labs completed a merger, and dbt Core version 2.0 open-sourced the Fusion engine, a Rust rewrite that parses large projects considerably faster.

**SQLMesh** is the main open-source alternative. It tracks the state of models and their columns, which allows it to determine what actually changed and to avoid rebuilding models unnecessarily. Its ownership has changed too: Fivetran acquired its creators in 2025 and later donated SQLMesh to the Linux Foundation for neutral governance.

**Python-based transformation**, using a dataframe library or a query engine directly, suits work that SQL expresses badly, such as complex matching, iterative algorithms, or anything requiring libraries.

**Hand-written SQL with a runner script** remains a legitimate choice for very small projects, provided someone maintains the ordering by hand.

### How they compare

| Option | Strongest for | Main trade-off |
|---|---|---|
| dbt | Teams wanting the largest ecosystem and the most available expertise | Roadmap now tied to a larger commercial owner |
| SQLMesh | Teams that want change detection and neutral governance | Smaller community and fewer available packages |
| Python transformation | Logic that SQL expresses poorly | Loses SQL's readability for analysts |
| Plain SQL scripts | Very small, stable projects | No graph, no tests, no lineage |

### Why the sports platform uses dbt

The platform's transformations are almost entirely relational work: resolving aliases, reconciling sources, aggregating appearances, and calculating percentiles. That is SQL's natural territory. The deciding factors were the ecosystem, the ease of expressing tests next to models, and the fact that its concepts are widely understood, which matters for a project meant to be read by others.

The platform does use Python for two specific jobs: parsing captured pages and fuzzy entity matching. Both are poor fits for SQL, and forcing them into SQL for the sake of consistency would have made them harder to test.

Two other framework features earn their place in almost every project. The first is putting business rules in data rather than in code, so that a score can be changed without editing SQL.

```sql
-- transform/models/mart/talent_score.sql  (simplified)
-- Weights come from seeds/talent_weights.csv; tier selects the right column.
select
    p.player_id,
    p.season_id,
    round(
        sum(component_value * case when p.data_tier = 'A' then w.wa else w.wb end)
        / nullif(sum(case when p.data_tier = 'A' then w.wa else w.wb end), 0)
    , 1) as talent_score
from {{ ref('player_components') }} p   -- inline CTE in practice
join {{ ref('talent_weights') }} w using (component)
where p.minutes_played >= 270
group by p.player_id, p.season_id
```

Keeping the weights in the seed file is the whole trick: changing a weight is a one-line CSV edit and a reviewable commit, not a SQL change buried in a model.

All models in this project use `materialized='table'`. Incremental materialisation is not currently configured, since full rebuilds on the project's current data volume take only a few seconds.


### Qualifiers and objections

SQLMesh would have handled the same work, and its change-detection model is a real advantage on large projects where rebuild costs are significant. For a platform of this size, running against a single database, that advantage is smaller than the ecosystem advantage.

That said, the ownership changes in this part of the market are a reason to think about lock-in now rather than later.

## Protect yourself from lock-in

The third decision is about limiting the cost of a future change. The claim is that most of the value of a transformation layer lives in your SQL and your tests, and that a careful project keeps it there.

### Keep the logic in SQL, not in macros

Frameworks offer templating features that can generate SQL dynamically. Used sparingly, they remove repetition. Used heavily, they create a codebase that only that framework can run, and that new colleagues cannot read.

The rule I follow is that a model should be understandable to someone who knows SQL but not the framework, with templating limited to references, configuration, and the occasional simple loop.

### Keep business rules in data, not in code

Weights, thresholds, priorities, and mappings live in seed files, which are small CSV files loaded as tables. They are portable to any tool and readable by anyone, including people who will never open the repository.

### Keep tests declarative

Declarative tests, expressed as configuration, translate between tools far more easily than tests written as bespoke scripts. They are also easier for reviewers to check.

### Watch governance as a technical risk

Consolidation is visible across this market. One company now owns both of the leading open-source SQL transformation frameworks, and the orchestration market has consolidated as well. None of that breaks anything today, and both dbt Core and SQLMesh remain open source. It is simply a reason to know how much of your stack sits with one owner, and how quickly you could change direction if the licensing or pricing changed.

### Qualifiers and objections

Avoiding advanced framework features has a cost, because some of them genuinely reduce repetition. The judgment is about proportion. A macro that standardises a date calculation is worth it, while a macro that generates entire models usually is not.

## Conclusion

The folder of SQL scripts is not wrong because SQL is wrong. It is wrong because it holds no record of order, no proof of correctness, and no way to see what a change will break.

Choose a transformation layer by first understanding what a framework buys you, which is a dependency graph, tests beside the models, safe environments, and lineage. Compare the leading options on philosophy and governance rather than on feature lists. Then keep your logic in portable SQL, your rules in data, and your tests declarative, so that the choice remains yours to revisit.

**Transformations are code, not queries.**

The numbers your organisation argues about are produced in this layer. Make them reviewable, testable, and explainable, and most of those arguments become short.

As a first step, pick the single most important number your team reports and try to trace it back to its source tables. If you cannot do that in a few minutes, your transformation layer is telling you what to fix first.

*This is the ninth article in a series on data engineering lessons from building pipelines on external sources. The next article covers storage choices, including when a single database is enough and when files are the better answer.*

**Tags:** Data Engineering, Analytics Engineering, dbt, SQL, Data Modeling
