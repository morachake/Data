{{ config(severity='warn') }}
-- WARN level test (severity: warn)
-- Seasons that have data but are below Tier C coverage (< 70% matches with result).
-- Triggers a review of the source or spider.

select
    season_id,
    pct_matches_with_result,
    tier
from {{ ref('league_season_coverage') }}
where
    pct_matches_with_result is not null
    and (tier is null or pct_matches_with_result < 70)
    -- Only warn when we have at least some data (avoid false positives for new seasons)
    and pct_matches_with_result > 0
