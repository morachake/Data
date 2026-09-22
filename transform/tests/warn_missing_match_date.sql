{{ config(severity='warn') }}
-- WARN level test (severity: warn)
-- Match records missing a date reduce the quality of timeline analysis.
-- A high proportion of missing dates should trigger a review of the source.
-- Returns (season_id, pct_without_date) rows where > 50% of matches lack a date.

with season_stats as (
    select
        season_id,
        count(*)                                            as total,
        count(case when match_date is null then 1 end)      as without_date
    from {{ ref('match') }}
    group by season_id
)

select
    season_id,
    total                                                   as total_matches,
    without_date                                            as matches_missing_date,
    round(100.0 * without_date / nullif(total, 0), 1)       as pct_without_date
from season_stats
where round(100.0 * without_date / nullif(total, 0), 1) > 50
