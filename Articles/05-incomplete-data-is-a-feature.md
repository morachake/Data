# Incomplete Data Is a Feature: Designing Honest Data Products

A dashboard looks equally confident whether it is built on complete data or on half of it. The chart has the same axes, the table has the same columns, and every number has the same number of decimal places. Nothing on the screen tells users that one value rests on a full year of detailed records while another rests on a few weeks of partial data.

I faced this problem while building a sports data platform that combines statistics from public sources across many competitions. For some competitions, the sources I was allowed to use included detailed lineups with substitution times, which made it possible to calculate exactly how many minutes each player played. For others, the available data stopped at match results and goalscorers. A single score applied to both would have presented very different levels of evidence as if they were identical.

The same situation appears in almost every organisation. A newly acquired business unit has only two years of history. One sales channel records every event while another records only daily totals. A merged customer dataset looks uniform in the warehouse, even though half of it came from a system that never captured email addresses.

This article is about **honest data products**. These are dashboards, reports, and datasets that measure how complete their data is, limit what they calculate to what the data can support, and show that completeness to the people who use them.

The principle fits in five words: **show what you don't know.**

It matters because people make decisions based on what they see. When incompleteness is hidden, users cannot tell a strong result from a weak one, and the product earns a level of trust that it has not deserved.

This article describes three practices. The first is to **measure completeness as data**, so that it can be stored, joined, and displayed. The second is to **calculate only what the data supports**, instead of filling gaps with estimates. The third is to **make every output explainable**, so that users can see where a number came from and why a result looks the way it does.

If you have ever defended a number in a meeting without knowing how much of the underlying data was missing, these practices are for you. We will start with measurement.

## Measure completeness as data

The first practice turns completeness from an assumption into a measurement. The claim is that completeness should be stored like any other fact, so that every part of a data product can use it.

### Decide what completeness means for your data

Completeness is not a single number. It depends on what the product needs. For an order pipeline, completeness might mean the share of orders with a customer identifier, a delivery date, and a payment status. For a customer analytics product, it might mean the share of customers with a known region and acquisition channel.

In the sports platform, a coverage model built with dbt calculates several percentages for every competition and season after each pipeline run. These include the percentage of matches with a recorded result, the percentage of goals with a named scorer, the percentage of matches with lineup data, and the percentage of players with a known date of birth.

The model that produces those percentages, and the tier derived from them, is ordinary SQL.

```sql
-- transform/models/core/league_season_coverage.sql  (simplified)
with coverage as (
    select
        m.season_id,
        round(100.0 * count(case when status = 'played' then 1 end)
              / nullif(count(*), 0), 2)                                as pct_matches_with_result,
        round(100.0 * count(case when g.player_id is not null then g.goal_id end)
              / nullif(count(g.goal_id), 0), 2)                        as pct_goals_with_scorer,
        round(100.0 * count(distinct a.match_id)
              / nullif(count(distinct m.match_id), 0), 2)              as pct_matches_with_lineups
    from {{ ref('match') }} m
    left join {{ ref('goal') }}       g using (match_id)
    left join {{ ref('appearance') }} a using (match_id)
    group by m.season_id
)
select
    season_id,
    pct_matches_with_result,
    pct_goals_with_scorer,
    pct_matches_with_lineups,
    case
        when pct_matches_with_result >= 95
         and coalesce(pct_goals_with_scorer,  0) >= 80
         and coalesce(pct_matches_with_lineups, 0) >= 70 then 'A'
        when pct_matches_with_result >= 90
         and coalesce(pct_goals_with_scorer, 0) >= 50   then 'B'
        when pct_matches_with_result >= 70               then 'C'
        else null
    end as tier
from coverage
```

The thresholds are percentages (not fractions), they are visible in one place, and changing one is a reviewable commit rather than a change of behaviour nobody notices. A date-of-birth threshold also feeds into Tier A, not shown here for brevity.


### From measurements to tiers

Those percentages are then combined into a single tier for each competition and season, because a tier is easier for both models and users to act on than five separate percentages.

| Tier | Data available | What the platform calculates |
|---|---|---|
| A | Results, scorers, and lineups with minutes | Full player metrics, including minutes played and rates per 90 minutes |
| B | Results and scorers | Reduced player metrics based on appearances and goals |
| C | Results only | Team-level context, with no player metrics |

Because the tier is stored in a table, every downstream model can filter on it, join to it, and display it. Completeness stops being something that only a data engineer knows and becomes something that the product itself knows.

### Qualifiers and objections

The thresholds that separate one tier from another are choices, not laws of nature. A reasonable objection is that they are arbitrary. They are, however, explicit, which makes them open to review and adjustment. A product that hides its assumptions about completeness still relies on thresholds. It simply relies on thresholds that nobody can see or challenge.

Once completeness has been measured, the product has to act on it.

## Calculate only what the data supports

The second practice limits what a product calculates. The claim is that a metric which the data cannot support should not be produced at all, even when an estimate would be easy to calculate.

### Treat estimates and measurements differently

**Imputation** means filling missing values with estimated ones. In the sports platform, lineup data is unavailable for lower-coverage competitions, so rather than leaving those players absent from the scout shortlist entirely, the model uses Wikipedia squad and career data to estimate minutes played. These estimated values look like measured ones once they reach the dashboard, which is the risk.

The platform manages this by labelling every player row with a `data_tier` column from `league_season_coverage`. The tier tells downstream models and users that minutes for a Tier B or C player come from an estimate, not a measured lineup.

```sql
-- transform/models/mart/player_season.sql  (simplified, Tier B path)
-- When lineup appearances are unavailable, fall back to Wikipedia squad data.
wiki_squad as (
    select
        player_id,
        season_id,
        1 as appearances,
        (greatest(coalesce(s.appearances, 5), 3) * 90) as minutes_played   -- estimate
    from {{ ref('fct_player_squad') }} s ...
)
...
select
    ps.player_id,
    ps.season_id,
    coalesce(cv.tier, 'C')   as data_tier,   -- tells the reader what kind of data this is
    ps.appearances,
    ps.minutes_played,       -- measured for Tier A; estimated for Tier B/C
    ...
from combined ps
join {{ ref('league_season_coverage') }} cv using (season_id)
```

A stricter design would null out estimated metrics so that no estimate reaches the dashboard. The current approach instead keeps players visible across all tiers and relies on the `data_tier` label to communicate the quality of each row. Both choices have costs: hiding estimates protects users from confusion; surfacing them with a label keeps the shortlist populated even for lower-quality competitions.


### Match test severity to the kind of problem

The same principle shapes how data tests behave. Some problems mean that data is **wrong**, while others mean that it is **incomplete**. Treating both in the same way leads to one of two failures. Either every gap stops the pipeline, and people learn to ignore test results, or nothing stops it, and real errors pass through unnoticed.

The sports platform divides its dbt tests by severity. Six are error tests that stop the build, such as a test that fails when a match lists the same team as both home and away, or when a team name cannot be linked to an internal identifier. Six are warning tests that record a problem and allow the build to continue, such as tests for coverage falling below Tier C, or for season totals that differ from the expected count.

```yaml
# transform/models/core/schema.yml  (illustrative pattern)
- name: match
  columns:
    - name: home_team_id
      tests:
        - not_null                # error: stops the build

# transform/tests/warn_player_dob_unknown.sql
# A custom warning test that counts the fraction of players without a DOB.
# If more than 40 % are unknown, the test records a warning but the build continues.
```

The general rule is that wrong data should stop the pipeline, while incomplete data should be measured and shown.

### Qualifiers and objections

Some users will prefer an estimate to a blank, and in some settings a clearly labelled estimate is genuinely useful, as in a sales forecast. The problem is not estimation itself. The problem is estimation that looks identical to measurement. When a product does provide estimates, they should be visibly marked and stored separately from measured values.

Measuring completeness and limiting calculations make the data honest. The final practice makes that honesty visible to users.

## Make every output explainable

The third practice helps users understand what they see. The claim is that people trust results that they can trace, question, and explain.

### Keep provenance on every row

**Provenance** is the record of where a piece of data came from. In the sports platform, every row carries a source identifier and the address of the page it came from, from the raw layer all the way to the core models. As a result, any number on the dashboard can be traced back to its origin. When a user questions a result, the answer is a link rather than an investigation.

In a business setting, the same idea means carrying the source system and extraction time with each record, so that an analyst can see whether a figure came from the billing system or the CRM, and when it was collected.

### Put model choices where users can read them

Every score or ranking contains judgments. In the sports platform, a talent score combines several components, and each weighting is a choice. How much should playing time count compared with goals scored? How much should the strength of a competition matter? There is no single correct answer to either question.

The weights are therefore stored in a dbt seed, which is a small CSV file that dbt loads as a table, instead of being written into application code.

```csv
# transform/seeds/talent_weights.csv
component,tier_a_weight,tier_b_weight
minutes_share,0.25,0.30
output_per90,0.25,0.25
position_percentile,0.20,0.20
age_factor,0.10,0.10
progression_delta,0.10,0.05
league_strength,0.10,0.10
```

Anyone can read the file, disagree with a weight, and see exactly what changing it would do. The file also shows how the score adapts to each tier. Tier B gives slightly more weight to `minutes_share` and slightly less to `progression_delta`, reflecting that progression estimates are less reliable when minutes are themselves estimated.

A lead-scoring model in a sales team or a risk score in a lending team can be made transparent in the same way, by storing its weights in a place that reviewers can read and discuss.

### Explain empty results

Empty results need explaining more than any other output. The sports platform includes a shortlist that lets users filter players by position, age, competition, minutes played, and score. When no players match, a generic message such as "no players match your filters" gives users nothing to act on.

Instead, the shortlist shows a filter funnel, which lists the number of players remaining after each filter is applied. The example below uses illustrative numbers.

| Filter applied | Players remaining |
|---|---|
| All players | 4,812 |
| Selected competitions | 1,106 |
| Competitions with lineup data (Tier A) | 0 |

In a case like this, the reason becomes obvious immediately. The selected competitions have no lineup data, so no player in them has recorded minutes, and a minimum-minutes filter can never be satisfied. The funnel turns an empty screen into an explanation. Any product with filters, such as a search page or a customer segmentation tool, can use the same technique.

Building the funnel requires only that filters be applied one at a time, with the count recorded after each step.

```python
# serving/filter_funnel.py
import streamlit as st

def show_filter_funnel(df, filters: list[tuple[str, callable]]):
    """filters: ordered list of (label, fn(df) -> boolean Series)."""
    rows = [("All players in mart", len(df))]
    current = df
    for label, fn in filters:
        current = current[fn(current)]
        rows.append((label, len(current)))
    if len(current) > 0:
        return current
    # Empty result: surface the funnel so the user can see where it zeroed out.
    st.dataframe(rows, ...)
    return None

# Usage in serving/app.py
filters = [
    ("Selected leagues",              lambda d: d.league_id.isin(selected_leagues)),
    ("Competitions with lineup data (Tier A)", lambda d: d.tier == "A"),
    ("Age within range",              lambda d: d.age.between(age_min, age_max)),
    (f"Minutes ≥ {min_minutes}",      lambda d: d.minutes_played.fillna(0) >= min_minutes),
]
```

Writing filters as an ordered list rather than as one long boolean expression is the whole trick, and it costs nothing in performance at this scale.


### Qualifiers and objections

Provenance columns make every table wider, and funnels require extra work to build. For a product with a single complete source, some of this effort may be unnecessary. For a product built on uneven sources, it often makes the difference between a result that users trust and one that they quietly ignore.

## Conclusion

A dashboard does not have to look equally confident about everything. It can show users which numbers rest on detailed data, which rest on less, and which could not be calculated at all.

Honest data products measure completeness and store it as data, using tiers that every model can read. They calculate only what the data can support, avoid disguising estimates as measurements, and match the severity of each test to the kind of problem it detects. They also make every output explainable through provenance, readable model choices, and empty results that explain themselves.

**Show what you don't know.**

Users will forgive a product for having gaps, but they will not forgive it for hiding them. Every honest blank you show makes every number beside it more believable.

Try this on one dashboard you maintain. Next to its main number, add a count of the records that were excluded and the reason they were excluded. That single line can change how people read everything else on the page.

*This is the fifth article in a series on data engineering lessons from building pipelines on external sources. The next article covers a score that quietly excluded an entire group, and what it teaches about ranking mixed populations.*

**Tags:** Data Engineering, Data Quality, dbt, Data Products, Analytics Engineering
