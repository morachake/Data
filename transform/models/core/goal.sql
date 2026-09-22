{{
  config(
    materialized='table',
    tags=['core', 'partitioned']
  )
}}

/*
  goal — resolved goal events joined to core.match and core.player.
  Phase 2+: populated once PSL official or similar source provides scorers.
  Until then, this table is empty but the schema is ready.
*/

with stg as (
    select * from {{ ref('stg_goal') }}
),

matches as (
    select
        match_id,
        season_id,
        home_team_id,
        away_team_id,
        match_date
    from {{ ref('match') }}
),

aliases as (
    select alias, team_id, source_id
    from {{ ref('team_alias') }}
)

select
    g.id::text                                        as goal_id,
    m.match_id,
    null::text                                        as player_id,   -- Phase 2: entity resolution
    ta.team_id,
    g.minute,
    g.is_own_goal,
    g.is_penalty,
    g.scorer_raw,
    g.source_id,
    g.source_url
from stg g
join matches m
    on  m.match_date   = g.match_date
    and m.home_team_id = (
            select team_id from aliases
            where alias = g.home_team_raw and source_id = g.source_id
            limit 1
        )
    and m.away_team_id = (
            select team_id from aliases
            where alias = g.away_team_raw and source_id = g.source_id
            limit 1
        )
left join aliases ta on ta.alias = g.team_raw and ta.source_id = g.source_id
