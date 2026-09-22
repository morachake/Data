{{
  config(
    materialized='view',
    tags=['partitioned']
  )
}}

/*
  stg_match — normalised match rows from all sources.

  One row per (source, league, season, home_team_raw, away_team_raw) combination.
  Deduplication and source priority are applied downstream in core/match.sql.
*/

select
    id,
    league_id,
    season,
    trim(home_team_raw)     as home_team_raw,
    trim(away_team_raw)     as away_team_raw,
    home_goals,
    away_goals,
    match_date,
    round,
    status,
    source_id,
    source_url,
    run_id,
    loaded_at

from {{ source('staging', 'stg_match') }}

where
    home_team_raw is not null
    and away_team_raw is not null
    and home_goals  is not null
    and away_goals  is not null
    and home_team_raw != away_team_raw   -- sanity guard; caught by error test too
