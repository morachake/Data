{{
  config(
    materialized='table',
    tags=['mart']
  )
}}

/*
  One row per goalkeeper appearance, with goals conceded while he was on
  the pitch. Only Tier A league-seasons produce rows: we need lineups
  with minutes and a resolved player_id.
*/

with gk as (
    select
        a.match_id,
        a.player_id,
        a.team_id,
        a.started,
        a.minutes_played,
        0::int   as min_on,
        999::int as min_off
    from {{ ref('appearance') }} a
    join {{ ref('player') }} p using (player_id)
    where {{ position_bucket('p.position') }} = 'GK'
      and a.player_id is not null
      and coalesce(a.minutes_played, 0) > 0
),

conceded as (
    select gk.match_id, gk.player_id, count(g.goal_id) as goals_conceded_on_pitch
    from gk
    left join {{ ref('goal') }} g
           on g.match_id = gk.match_id
          and g.team_id is not null
          and g.team_id <> gk.team_id
          and coalesce(g.minute, 0) >= gk.min_on
          and coalesce(g.minute, 999) <= gk.min_off
    group by gk.match_id, gk.player_id
)

select
    e.season_id,
    gk.match_id,
    gk.player_id,
    gk.team_id,
    gk.started,
    gk.minutes_played,
    c.goals_conceded_on_pitch,
    e.expected_conceded * gk.minutes_played / 90.0 as expected_conceded_on_pitch,
    (gk.started and gk.min_off = 999 and c.goals_conceded_on_pitch = 0) as clean_sheet
from gk
join conceded c using (match_id, player_id)
join {{ ref('gk_expected_conceded') }} e
  on e.match_id = gk.match_id
 and e.team_id  = gk.team_id
