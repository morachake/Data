# When Your Upstream Disappears: Designing Pipelines for Source Failure

The request returned a status code of 200, which means the server reported success. The response contained a page title and a logo. It did not contain a single row of the data the pipeline had come to collect. The page that used to hold that data now redirected to a homepage, and the homepage built its content in the browser using JavaScript, so a scraper reading the raw HTML received an empty shell. Nothing crashed, and no error was raised. A pipeline that only checked whether its requests succeeded would have recorded a successful run and moved on.

I ran into exactly this situation while building a sports data platform that collects statistics from public websites. An official results page that search engines still indexed had quietly stopped serving results. The experience changed how I think about failure, because the failures that do the most damage are not the ones that stop a pipeline. They are the ones that let it keep running.

This article is about **designing pipelines for source failure**. It applies to any pipeline that depends on data it does not control, including scraped websites, third-party APIs, partner file drops, and even internal systems owned by other teams.

The central rule fits in five words: **zero rows is an error.**

Every external source is temporary. Websites are redesigned, links move, APIs are versioned and retired, and file formats change without notice. The question is not whether this will happen to your sources. The question is whether your pipeline will notice when it does.

This article covers three steps. The first step is to **recognise silent failures**, which look like success. The second step is to **detect them with expectations**, by comparing what arrived with what should have arrived. The third step is to **recover through redundancy**, so that one failing source does not stop the whole platform.

If you have ever discovered a broken dashboard weeks after the data stopped flowing, these steps are designed to shorten those weeks to a single run. We will begin with recognition.

## Recognise silent failures

The first step is accepting that the most damaging failures often raise no errors at all. The claim is that exit codes measure whether code ran, not whether data arrived.

### How sources fail quietly

A loud failure is easy to handle. A timeout, a server error, or a refused connection stops the pipeline, someone is alerted, and the problem is fixed. A silent failure returns a normal response that contains less data than before, or none at all.

Silent failures take several common forms. A **redirect** sends a request for one page to a different page, so the scraper receives a valid response from the wrong place. **Client-side rendering** means a page's content is built by JavaScript after it loads, so a scraper that reads the raw HTML sees only a skeleton. A **schema change** in an API renames or removes a field, so the pipeline keeps running but fills a column with nulls. A **format change** in a partner's file moves a column, so values land in the wrong fields.

### Small details fail quietly too

Some silent failures are caused not by the source changing but by details that were never handled correctly in the first place.

The sports platform provides a good example. Some of its sources use an en dash rather than a hyphen in season labels, such as "2025–26" instead of "2025-26". A scraper that builds page addresses with an ordinary hyphen requests pages that do not exist. Scores in some tables are written with an en dash and in others with a hyphen, so a parser that expects only one form silently skips the other. Each of these mistakes produces empty or partial results instead of an error.

### Qualifiers and objections

Not every empty result is a failure. A sports competition with no matches during a scheduled break, or a sales feed on a public holiday, can legitimately return nothing. The point is not that every empty result is wrong. The point is that each one must be explained before it is accepted.

A common objection is that monitoring already covers failures. It does, but only when the monitoring measures data. Monitoring that tracks whether jobs succeeded will report a healthy pipeline while the data quietly disappears.

Recognising silent failures is useful only if the pipeline can detect them automatically, and detection requires expectations.

## Detect failures with expectations

The second step compares what arrived with what should have arrived. The claim is that a pipeline can detect missing data only when it knows how much data to expect.

### Compare each run with the previous run

In the sports platform, raw data is partitioned by source, league, and season. Because of this, the pipeline can compare how many items each partition produced against a manifest written by the previous run. If a partition that previously returned hundreds of rows suddenly returns none, the run fails.

The check is short, and the important detail is that it raises an exception rather than writing a log line. The pattern below shows the intent; run statistics are currently written as JSON manifest files under `data/raw/_manifests/` rather than to a database table, but the logic is the same.

```python
# aspirational pattern using a run-log table
def check_partition(cursor, source_id: str, league_id: str, season: str, items_now: int) -> None:
    cursor.execute(
        """
        select max(items_total)
        from ops.run_log
        where source_id = %s and league_id = %s and season = %s and status = 'success'
        """,
        (source_id, league_id, season),
    )
    (previous,) = cursor.fetchone()
    if previous and items_now == 0:
        raise RuntimeError(
            f"{league_id}/{season}: collected 0 items, previous good run collected {previous}"
        )
```

Without this check, the same situation produces a green run and an empty table.


The raw layer also stores a **content hash** for every item. A content hash is a short fingerprint calculated from the content itself. When the hash is unchanged, the page has not changed and the parser can skip it. When the hash changes and the number of extracted items falls sharply at the same time, the most likely explanation is a layout change.

Calculating it costs almost nothing, provided the content is serialised in a stable order first.

```python
# ingestion/ingestion/pipelines.py  (simplified)
import hashlib, json

def content_hash(payload) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.md5(canonical.encode("utf-8")).hexdigest()
```

Sorting the keys matters. Without it, an unchanged page can produce a different hash simply because a dictionary was built in a different order, and the pipeline will reprocess everything for no reason.


Any pipeline can apply the same idea. An orders feed can compare today's row count with the same weekday last week, and an API integration can compare the number of non-null values in each field with its recent average.

### Check against independent facts

Independent facts provide another kind of expectation. A completed sports season should contain a known number of matches. A month of transactions should reconcile with the total in the finance system. A customer export should contain roughly as many records as the customer table in the source application.

These expected values must be treated as data rather than as constants, because they can be wrong too. While building the sports platform, I found a public reference page whose season summary listed 260 matches, while the league table on the same page showed eighteen teams each playing 34 games, which implies 306 matches. Both figures cannot describe the same complete season. For that reason, the platform stores expected counts in configuration, together with where each value came from, instead of calculating them from a formula. When collected data and an expected value disagree, the outcome is an investigation rather than automatic trust in either number.

In dbt, that comparison is a singular test, which is a query that must return no rows for the build to pass.

```sql
-- transform/tests/assert_season_totals.sql  (severity: warn)
with actual as (
    select season_id, count(*) as matches
    from {{ ref('match') }}
    group by season_id
)
select
    e.season,
    e.expected_matches,
    a.matches as actual_matches
from {{ ref('season_checks') }} e   -- seeds/season_checks.csv
left join actual a on a.season_id like '%' || e.season
where a.matches != e.expected_matches
  or a.matches is null
```

The seed `season_checks.csv` stores the expected count alongside where each figure came from, so that when the test flags a discrepancy the first question is already answered. This test runs at warning severity — it records the mismatch and continues the build, because a count difference is worth investigating rather than blocking publication.


### Qualifiers and objections

Expectations need maintenance. Seasons are shortened, schedules change, and business volumes shift. Each legitimate exception must be recorded, or the checks will fail for valid reasons and people will learn to ignore them.

Some engineers object that failing a run because of an empty partition is too strict. The alternative is a pipeline that publishes incomplete data while reporting success. A false alarm costs one investigation, while a missed failure costs trust in every report built on the affected data.

Detecting a failure solves half of the problem. The other half is continuing to operate while the failure is fixed.

## Recover through redundancy

The third step keeps a platform working when a source fails. The claim is that recovery must be designed before a failure happens, through multiple sources, rules for choosing between them, and raw data that can be processed again.

### Use more than one source for important data

Important datasets should have more than one permitted source whenever possible. In the sports platform, historical results come from one public reference source and are cross-checked against a second, independent archive. Official sources are added once their terms of service have been reviewed.

Some websites that hold current data restrict automated collection in their terms. They are not used as pipeline inputs. A person can still consult them manually to check a suspicious value.

### Decide which source wins before sources disagree

Multiple sources will sometimes disagree, so the rule for choosing between them should be decided in advance. In the sports platform, dbt reconciliation models apply a fixed priority order encoded in `config/sources.yml`. When priorities are equal, the most recently loaded record wins.

Every disagreement is written to a conflict log. The log schema records which two sources disagreed and which one was preferred.

```sql
-- transform/models/core/conflict_log.sql  (columns)
-- entity_type   e.g. 'match'
-- entity_id     season + teams composite key
-- field         e.g. 'score'
-- source_a_id   first source (e.g. 'wikipedia_season')
-- source_a_value  that source's value (e.g. '2-1')
-- source_b_id   second source
-- source_b_value  second source's value
-- winning_source  which source the model preferred
-- resolution_rule  e.g. 'source_priority: psl_official=1, wikipedia=2, rsssf=3'
-- logged_at
```

The conflict log explains every chosen value, and it also acts as an early warning. A sudden increase in conflicts for one dataset usually means one of its sources has started returning something different. When the highest-priority source disappears, the next source takes over, and the log records exactly when that happened.

A manual override layer (a seed file `transform/seeds/overrides.csv`) is the intended tie-breaker that wins before all other rules, but it is not yet wired into the reconciliation model. Implementing that final step — checking the seed before applying source priority — is the direct next enhancement to the recovery design.


### Keep raw data you can replay

Every collected item is stored exactly as it arrived, in files that are never edited. When a parser bug is discovered, the parser is fixed and the stored raw data is processed again. The original pages or API responses do not need to be requested a second time, which matters when they no longer exist.

### Handle JavaScript sources carefully

When a permitted source moves its content behind JavaScript, the first step is to open the browser's developer tools and inspect the network requests the page makes. Many such pages load their data from a structured endpoint that returns JSON, which is easier and more reliable to read than rendered HTML. If no usable endpoint exists, a browser automation tool such as Playwright can render the page, but only for that source and only if its terms allow automated access. If neither option is possible, the gap is recorded rather than filled from a source the pipeline is not allowed to use.

### Qualifiers and objections

Redundancy has costs. More sources mean more collectors, more parsers, and more reconciliation logic, and the conflict log needs regular attention. For a pipeline that depends on one stable internal system, that cost may not be justified. For a pipeline built on external sources, it is the price of remaining useful when one of them changes.

## Conclusion

A page that returns a logo instead of data does not raise an error. That is precisely why silent failures are dangerous: they look like success until someone notices the numbers are missing.

Designing for source failure begins with recognising that redirects, client-side rendering, schema changes, and small formatting details can all produce empty results without errors. It continues with detecting those failures through expectations, including comparisons with previous runs and with independent facts that are themselves checked. It ends with recovery, using multiple permitted sources, rules for choosing between them, a conflict log, and raw data that can be processed again.

**Zero rows is an error.**

Your users will never see the run that returned nothing. They will only see the report that was quietly wrong, and the pipeline is the only thing standing between those two moments.

This week, add one check to your pipeline that fails a run whenever a partition that previously contained data returns zero rows, unless an exception has been recorded. It takes only a few lines of code, and it catches a failure that job monitoring will miss.

*This is the third article in a series on data engineering lessons from building pipelines on external sources. The next article covers an architecture that keeps source-specific details upstream, so that better sources can be added later without rewriting the warehouse.*

**Tags:** Data Engineering, Data Pipelines, Data Quality, Observability, Data Reliability
