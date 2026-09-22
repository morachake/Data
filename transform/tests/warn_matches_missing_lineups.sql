{{ config(severity='warn') }}
-- WARN level test (severity: warn)
-- Matches without any appearance records have no lineup data.
-- Returns seasons where fewer than 30% of matches have lineups.

with season_lineup_stats as (
    select
        m.season_id,
        count(distinct m.match_id)                                           as total_matches,
        count(distinct a.match_id)                                           as matches_with_lineups
    from {{ ref('match') }} m
    left join {{ ref('appearance') }} a using (match_id)
    group by m.season_id
)

select
    season_id,
    total_matches,
    matches_with_lineups,
    round(100.0 * matches_with_lineups / nullif(total_matches, 0), 1)   as pct_with_lineups
from season_lineup_stats
where round(100.0 * matches_with_lineups / nullif(total_matches, 0), 1) < 30
