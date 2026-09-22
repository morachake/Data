{{
  config(
    materialized='table',
    tags=['core']
  )
}}

/*
  player_club_spell — ordered list of club stints per player.

  Phase 1: built from fct_player_career (Wikipedia career tables).
  Phase 2+: will incorporate appearance data to fill gaps and confirm
            transfer dates.
*/

with career as (
    select * from {{ ref('fct_player_career') }}
),

team_aliases as (
    select alias, team_id, source_id
    from {{ ref('team_alias') }}
),

resolved as (
    select
        c.player_id,
        ta.team_id,
        c.years         as start_season,
        null::text      as end_season,
        false           as loan,
        'wikipedia'     as source_id
    from career c
    left join team_aliases ta
           on ta.alias = c.club_raw
    where c.club_raw is not null
)

select
    row_number() over (order by player_id, start_season)::text  as spell_id,
    player_id,
    team_id,
    null::text                                                   as competition_id,
    start_season,
    end_season,
    loan,
    source_id
from resolved
where player_id is not null
