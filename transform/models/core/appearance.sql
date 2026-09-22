{{
  config(
    materialized='table',
    tags=['core', 'partitioned']
  )
}}

/*
  appearance — one row per player per match.
  Phase 2+: populated once PSL official lineups are available.
  Until then, empty but schema is live.
*/

with stg as (
    select * from {{ ref('stg_appearance') }}
),

matches as (
    select match_id, match_date, home_team_id, away_team_id
    from {{ ref('match') }}
),

aliases as (
    select alias, team_id, source_id
    from {{ ref('team_alias') }}
)

select
    a.id::text                                      as appearance_id,
    m.match_id,
    null::text                                      as player_id,   -- Phase 2: entity resolution
    ta.team_id,
    a.started,
    a.minutes_played,
    a.shirt_number,
    a.position_raw,
    a.player_raw,
    a.source_id,
    a.source_url
from stg a
join matches m
    on  m.match_date   = a.match_date
    and m.home_team_id = (
            select team_id from aliases
            where alias = a.home_team_raw and source_id = a.source_id
            limit 1
        )
    and m.away_team_id = (
            select team_id from aliases
            where alias = a.away_team_raw and source_id = a.source_id
            limit 1
        )
left join aliases ta on ta.alias = a.team_raw and ta.source_id = a.source_id
