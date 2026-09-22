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
    trim(team_raw)         as team_raw,
    trim(player_raw)       as player_raw,
    trim(nationality_raw)  as nationality_raw,
    trim(position_raw)     as position_raw,
    shirt_number,
    source_id,
    source_url,
    loaded_at

from {{ source('staging', 'stg_squad') }}

where player_raw is not null
