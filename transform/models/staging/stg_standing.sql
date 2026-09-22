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
    trim(team_raw)   as team_raw,
    position,
    played,
    won,
    drawn,
    lost,
    goals_for,
    goals_against,
    goal_diff,
    points,
    source_id,
    source_url,
    run_id,
    loaded_at

from {{ source('staging', 'stg_standing') }}

where
    team_raw is not null
    and season   is not null
