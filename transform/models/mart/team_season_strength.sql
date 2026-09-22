{{
  config(
    materialized='table',
    tags=['mart']
  )
}}

/*
  team_season_strength — performance per team per season.
  Used as a covariate in talent_score (league difficulty adjustment).
*/

select
    s.season_id,
    s.team_id,
    s.league_id,
    s.season,
    s.played,
    s.won,
    s.drawn,
    s.lost,
    s.goals_for,
    s.goals_against,
    s.goal_diff,
    s.points,
    s.position,
    -- points per game
    case when s.played > 0
        then round(s.points::numeric / s.played, 3)
        else null
    end                             as ppg,
    -- goal difference per game
    case when s.played > 0
        then round(s.goal_diff::numeric / s.played, 3)
        else null
    end                             as gd_per_game
from {{ ref('standings') }} s
