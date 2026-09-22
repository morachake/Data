{{
  config(
    materialized='table',
    tags=['core']
  )
}}

/*
  season — one row per (competition, season_label) pair seen in stg_match.
  expected_teams comes from the team seed (count of active teams per competition).
*/

with match_seasons as (
    select distinct
        league_id   as competition_id,
        season      as season_label
    from {{ ref('stg_match') }}
),

team_counts as (
    -- Count distinct teams that actually appeared in each season's matches.
    -- This is more accurate than the static team seed, which contains all
    -- historical teams across all eras (and would inflate expected_matches).
    select
        competition_id,
        season_label,
        count(distinct team_id) as expected_teams
    from (
        select league_id as competition_id, season as season_label, home_team_id as team_id
        from {{ ref('match') }}
        union
        select league_id, season, away_team_id
        from {{ ref('match') }}
    ) teams
    group by competition_id, season_label
)

select
    ms.competition_id || '_' || ms.season_label                           as season_id,
    ms.competition_id,
    ms.season_label,
    null::date                                                             as start_date,
    null::date                                                             as end_date,
    tc.expected_teams
from match_seasons ms
left join team_counts tc
       on tc.competition_id = ms.competition_id
      and tc.season_label   = ms.season_label
