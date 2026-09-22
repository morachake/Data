{{
  config(
    materialized='table',
    tags=['mart']
  )
}}

/*
  One row per team per played match: goals actually conceded vs goals an
  average defence would concede against this opponent at this venue.
  v1 note: the opponent's attack index includes this match (small leakage);
  acceptable for now, replace with a leave-one-out index later.
*/

with m as (
    select match_id, season_id, home_team_id, away_team_id, home_goals, away_goals
    from {{ ref('match') }}
    where status = 'played'
),

team_rows as (
    select season_id, match_id, home_team_id as team_id, away_team_id as opp_id,
           true as is_home, home_goals as gf, away_goals as ga
    from m
    union all
    select season_id, match_id, away_team_id, home_team_id,
           false, away_goals, home_goals
    from m
),

league_avg as (
    select season_id,
           avg(gf) filter (where is_home)     as home_gf_avg,
           avg(gf) filter (where not is_home) as away_gf_avg,
           avg(gf)                            as gf_avg
    from team_rows
    group by season_id
),

attack as (
    select t.season_id, t.team_id,
           avg(t.gf) / nullif(max(la.gf_avg), 0) as attack_index
    from team_rows t
    join league_avg la using (season_id)
    group by t.season_id, t.team_id
)

select
    tr.match_id,
    tr.season_id,
    tr.team_id,
    tr.opp_id,
    tr.is_home,
    tr.ga as goals_conceded,
    (case when tr.is_home then la.away_gf_avg else la.home_gf_avg end)
        * coalesce(a.attack_index, 1.0) as expected_conceded
from team_rows tr
join league_avg la using (season_id)
left join attack a
       on a.season_id = tr.season_id
      and a.team_id   = tr.opp_id
