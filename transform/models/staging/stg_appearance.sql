{{
  config(
    materialized='view',
    tags=['partitioned']
  )
}}

select
    id,
    league_id,
    season,
    match_date,
    trim(home_team_raw)  as home_team_raw,
    trim(away_team_raw)  as away_team_raw,
    trim(player_raw)     as player_raw,
    trim(team_raw)       as team_raw,
    started,
    minutes_played,
    shirt_number,
    position_raw,
    source_id,
    source_url,
    run_id,
    loaded_at

from {{ source('staging', 'stg_appearance') }}

where
    player_raw is not null
    and team_raw   is not null
    and (minutes_played is null or minutes_played between 0 and 120)
