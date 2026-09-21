select
    player_id,
    years,
    club_raw,
    appearances,
    goals,
    source_url
from {{ source('staging', 'player_career') }}
