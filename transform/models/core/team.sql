{{
  config(
    materialized='table',
    tags=['core']
  )
}}

/*
  team — master list of teams from the team seed.
  Supersedes dim_teams (the old name); fct_matches references this via team_alias.
*/

select
    team_id,
    team_name                       as name,
    country,
    competition_id,
    null::text                      as city,
    null::int                       as founded_year,
    null::text                      as wikipedia_title,
    null::text                      as wikidata_id
from {{ ref('seed_team') }}
