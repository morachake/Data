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
    trim(scorer_raw)     as scorer_raw,
    trim(team_raw)       as team_raw,
    minute,
    is_own_goal,
    is_penalty,
    source_id,
    source_url,
    run_id,
    loaded_at

from {{ source('staging', 'stg_goal') }}
