{{
  config(
    materialized='view',
    tags=['core', 'legacy']
  )
}}

/*
  fct_matches — BACKWARD-COMPATIBLE ALIAS for core.match.

  Existing dashboard and test references continue to work.
  New code should reference {{ ref('match') }} directly.
*/

select
    match_id,
    season_id,
    league_id,
    season,
    match_date,
    home_team_id,
    away_team_id,
    home_goals,
    away_goals,
    result,
    status,
    source_id       as source,
    source_url
from {{ ref('match') }}
