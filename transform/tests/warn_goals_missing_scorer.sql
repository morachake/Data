{{ config(severity='warn') }}
-- WARN level test (severity: warn)
-- Goals without a confirmed scorer reduce data quality below Tier A.
-- Returns seasons where scorer coverage is below 50%.

with season_goal_stats as (
    select
        m.season_id,
        count(g.goal_id)                                                    as total_goals,
        count(case when g.player_id is not null then g.goal_id end)         as goals_with_scorer
    from {{ ref('match') }} m
    left join {{ ref('goal') }} g using (match_id)
    group by m.season_id
    having count(g.goal_id) > 0
)

select
    season_id,
    total_goals,
    goals_with_scorer,
    round(100.0 * goals_with_scorer / nullif(total_goals, 0), 1)    as pct_with_scorer
from season_goal_stats
where round(100.0 * goals_with_scorer / nullif(total_goals, 0), 1) < 50
