{{
  config(
    materialized='table',
    tags=['mart']
  )
}}

/*
  league_strength — relative league difficulty used to adjust talent_score.

  Phase 4 approach:
    1. CAF association coefficient (UEFA-style): ratio of CAF CL / CC wins
       by clubs from each country (normalised).
    2. Average points per game of teams from that country in CAF competitions.
    3. These are blended into a 0–1 strength_index.

  Until CAF CL data is loaded, defaults to 1.0 for all leagues.
*/

with competition_strength as (
    -- When CAF_CL data is available, add the coefficient calculation here.
    -- Placeholder: 1.0 for all competitions until Phase 4 data is loaded.
    select
        competition_id,
        country,
        1.0::numeric                                    as raw_coefficient,
        1                                               as n_seasons_in_caf
    from {{ ref('competition') }}
    where type = 'league'
),

normalised as (
    select
        competition_id,
        country,
        raw_coefficient,
        round(
            raw_coefficient / nullif(max(raw_coefficient) over (), 0),
            4
        )                                               as strength_index
    from competition_strength
)

select
    competition_id,
    country,
    raw_coefficient,
    strength_index
from normalised
