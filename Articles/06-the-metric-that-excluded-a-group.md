# The Metric That Quietly Excluded a Whole Group: Scoring Mixed Populations Fairly

I opened the shortlist in my own sports analytics dashboard and asked what seemed like a simple question. I wanted to see goalkeepers aged 17 to 24, from several competitions, with at least 450 minutes played and a talent score of at least 50. The dashboard returned an empty table and a polite message suggesting that I lower the minimum score or check that the data build had run.

The build had run, and the filters were reasonable. The problem was the score itself. It rewarded goals and assists, and goalkeepers almost never record either. No goalkeeper could reach 50, no matter how well they played. An entire group had been excluded, not by any explicit rule, but by the shape of a formula.

I had designed that score myself, and none of its tests had flagged the problem. This article is about that kind of failure: a **composite score**, meaning a single number built from several measures, that works well for most of a population and silently fails for part of it. The same pattern appears far beyond sport. It appears in performance ratings that compare sales staff with support engineers, in product rankings that compare fast-moving goods with expensive durable items, and in risk scores that treat new customers the same way as long-standing ones.

The lesson fits in four words: **empty results are design reviews.**

This failure matters because it hides well. The score does not crash. It produces valid-looking numbers for everyone, and the affected group simply sits at the bottom of every list. Nobody notices until someone asks specifically about that group.

This article follows the problem through three steps. The first step is to **diagnose the formula** and understand why one score failed an entire segment. The second step is to **measure against context** by building a metric that fits what the affected group actually does. The third step is to **protect against thin evidence**, so that the new metric is not misled by small samples or by its own inputs.

If you own a score, a ranking, or a leaderboard, some group within it may already be invisible. Here is how I found mine.

## Diagnose the formula

The first step is understanding why a reasonable query returned nothing. The claim is that a single formula applied to a mixed population will fail any group whose contribution the formula does not measure.

### How the original score worked

The talent score combined six components for every player: the share of available minutes a player received, a goals-per-90 output percentile, a within-position percentile, an age factor that rewards younger players, a progression delta measuring year-on-year improvement in minutes share, and a league strength adjustment. Each component is weighted by values in a seed file, so the formula is transparent and changeable without editing SQL.

For attacking players, those components are reasonable. For goalkeepers, the `output_per90` component is close to zero for almost everyone, since goalkeepers almost never score goals or register assists. Even when goalkeepers were ranked only against one another, almost none of them had output to show. That component pulled every goalkeeper's total score down, and the position percentile offered no relief because it was also derived from output.

The general version of this problem is easy to recognise once it has a name. Whenever a score includes a component that one segment cannot produce, that segment is penalised for its role rather than for its performance.

### Why the empty result was useful

The empty table was frustrating, but it was also the most useful outcome available. A looser filter would have shown a few goalkeepers at the bottom of a longer list, and it would have been easy to conclude that goalkeepers in those competitions were simply weak.

An empty result forces a better question. When a reasonable request returns nothing, the problem is usually not the request. It is the design underneath it.

### Qualifiers and objections

The quickest fix would have been to lower the threshold for goalkeepers. That change would have produced results without changing what the score measured, and it would have hidden the problem instead of solving it. A goalkeeper's score would still have mainly described things that goalkeepers do not do.

Diagnosing the problem showed what was missing: a measure of what the affected group actually contributes.

## Measure against context

The second step builds a metric that fits the affected group. The claim is that performance should be judged against what was expected in each situation, rather than against a raw outcome that depends mostly on circumstances.

### Work with the data available

The sports platform relies on public sources, so it does not have data on saves or shots faced. For its best-covered competitions, however, it does have match results, lineups with substitution times, and the minute of every goal. That was enough to build a useful goalkeeper metric.

The idea is to compare the goals a goalkeeper actually conceded with the goals an average team would have been expected to concede against the same opponents, at the same venues, during the minutes that goalkeeper was playing. The general principle is to compare an outcome with a context-adjusted expectation, just as a sales team might compare a representative's results with the typical results for their territory.

### Estimate the expected outcome

For each team in each match, the model estimates how many goals the opponent would score against an average team. It starts with the competition's average scoring rate for home and away teams and then scales that rate by the opponent's attacking strength.

```sql
select
    tr.match_id,
    tr.team_id,
    tr.ga as goals_conceded,
    (case when tr.is_home then la.away_gf_avg else la.home_gf_avg end)
        * coalesce(a.attack_index, 1.0) as expected_conceded
from team_rows tr
join league_avg la using (season_id)
left join attack a
       on a.season_id = tr.season_id
      and a.team_id   = tr.opp_id
```

A strong attacking team playing at home is expected to score more goals, and a weaker team playing away is expected to score fewer. Each goalkeeper is then measured against that expectation.

### Attribute outcomes only to the right period

A goalkeeper who is substituted at half-time should not be charged for goals conceded after they left the pitch. The model therefore links each goal to the goalkeeper's time on the pitch, using the minute they came on and the minute they went off. In business data, the equivalent is attributing an account's results only to the period when a particular manager was responsible for it.

Goals scored in stoppage time create an edge case, because a goalkeeper who plays the entire match has no recorded minute of leaving. The model uses a **sentinel value**, which is a special value that represents a condition rather than a quantity. In this model, the value 999 means "played until the final whistle". Currently `gk_match` assigns this value unconditionally because substitution minutes are not yet parsed from the appearance data; when exact substitution times become available, the sentinel will apply only to unsubstituted goalkeepers.

```sql
-- transform/models/mart/gk_match.sql
999 as min_off   -- sentinel: played until final whistle
                 -- TODO: replace with coalesce(a.minute_off, 999) once appearance
                 --       minute_off is populated from lineup data
```

A sentinel value must never enter a calculation. If 999 were ever summed or averaged, it would distort every result that used it. In this model, it appears only in comparisons that decide whether a goal falls within a goalkeeper's time on the pitch.

### Qualifiers and objections

This measure reflects the whole defence as well as the goalkeeper. A team with strong defenders will concede fewer goals than expected, and its goalkeeper will benefit from that. The metric is therefore a reason to watch a goalkeeper more closely, not a final judgment of their ability. Context-adjusted metrics in other domains share this limitation, because they measure performance within a team or environment rather than in isolation.

A fairer measure is only reliable when enough evidence supports it, which is the subject of the final step.

## Protect against thin evidence

The third step protects the new metric from misleading results. The claim is that rankings built on small samples, or on inputs that include the outcome being judged, reward luck and design flaws instead of genuine performance.

### Shrink small samples

The main measure is **goals prevented per 90 minutes**, which is expected goals conceded minus actual goals conceded, scaled to a full match. A positive value means the goalkeeper conceded fewer goals than expected.

Without adjustment, a goalkeeper with a few fortunate matches could reach the top of the ranking. The model therefore applies **shrinkage**, which pulls each value toward zero according to how much evidence supports it.

```sql
-- transform/models/mart/gk_season.sql
{% set min_minutes = 270 %}      -- three full matches minimum
{% set shrink_minutes = 1800 %}  -- twenty full matches = full confidence

90.0 * (expected - conceded) / minutes
    * minutes / (minutes + {{ shrink_minutes }}.0) as goals_prevented_p90
```

The minimum of 270 minutes (three full matches) filters out goalkeepers with too little data to score at all. The shrinkage constant of 1,800 minutes means a goalkeeper at the minimum keeps 270/(270+1800) = 13% of their raw value, while a goalkeeper with a full season keeps most of it. The model also assigns a sample-confidence label to each goalkeeper, so the shortlist can show how much evidence supports each number. The same technique protects any ranking that includes both established and new members, such as product ratings with very different numbers of reviews.

### Compare like with like

The new model ranks goalkeepers only against other goalkeepers, using measures that actually vary between them. Playing time is compared within age bands, because a 19-year-old starting in goal is uncommon, while a 29-year-old starting in goal is normal.

A single competition rarely contains enough young goalkeepers for a meaningful ranking, so the model pools percentiles across all competitions for the same season. Ranking three people against one another produces percentiles that look precise but mean very little.

Both ideas, the age bands and the pooled comparison group, are expressed in the window functions themselves.

```sql
-- transform/models/mart/gk_season.sql  (simplified)
eligible as (
    select *,
           case when age < 21 then 'U21'
                when age <= 24 then 'U24'
                else '25+' end as age_band
    from enriched
    where minutes >= {{ min_minutes }}   -- 270
),

ranked as (
    select *,
           percent_rank() over (
               partition by season_label, age_band
               order by coalesce(minutes_share, 0)
           ) as pct_minutes_share,
           percent_rank() over (
               partition by season_label
               order by coalesce(goals_prevented_p90, 0)
           ) as pct_goals_prevented
    from eligible
)
```

The two window definitions encode two different judgments. Playing time is only meaningful against players of a similar age (partitioned by `age_band`), while goals prevented can fairly be compared across ages (partitioned only by season).


### Name the leakage

The expected-goals model has one known limitation. Each opponent's attacking strength is calculated from all of that opponent's matches, including the match being evaluated. This is a mild form of **leakage**, which occurs when information about an outcome influences the expectation used to judge that outcome. The effect is small in this case, and it is documented in the model. A stronger version would calculate each opponent's strength while excluding the match in question.

Leakage is usually discussed in machine learning, but it can appear just as easily in ordinary SQL analytics. Any benchmark calculated from a group that includes the item being benchmarked has the same weakness.

The correction is to compute each benchmark while excluding the row being judged, which window functions make straightforward.

```sql
-- leave-one-out opponent strength: exclude the match being evaluated
select
    t.match_id,
    t.opponent_id,
    (
        (sum(t.opponent_goals) over (partition by t.season_id, t.opponent_id) - t.opponent_goals)
        / nullif(count(*) over (partition by t.season_id, t.opponent_id) - 1, 0)
    ) / nullif(l.league_avg_goals, 0) as attack_index_excluding_this_match
from team_match_rows t
join league_averages l using (season_id)
```

The pattern of subtracting the current row from a window total is worth remembering, because it applies to any benchmark, including comparing a shop with its region's average or an employee with their team's.


### Qualifiers and objections

Shrinkage can slow the recognition of a genuinely strong newcomer who has only a small amount of history. That is a real cost. A confidence label reduces it by showing that the newcomer is promising but not yet proven, which is an accurate description of what the data can support.

## Conclusion

The empty table of goalkeepers was not a bug in the filters. It was the dashboard revealing that the score had never been designed for part of the population it ranked.

Fixing the problem took three steps. Diagnosing the formula showed that one score could not fairly measure every role. Measuring against context produced a metric based on expected outcomes during each person's own time of responsibility. Protecting against thin evidence added shrinkage, fair comparison groups, and an honest record of leakage.

**Empty results are design reviews.**

Every score you publish makes a claim about everyone it ranks, including the people it was never designed for. The groups your formula cannot see will not complain. They will simply never appear.

Try this with one ranking you own. Filter it by each segment in turn, such as each role, product category, or region, and look at where each group's scores sit. If one group is packed at the bottom, the formula may be telling you something about itself.

*This is the sixth article in a series on data engineering lessons from building pipelines on external sources. The next article covers choosing an ingestion stack: frameworks, browser automation, and when to buy instead of build.*

**Tags:** Data Engineering, Analytics Engineering, Data Modeling, SQL, Data Quality
