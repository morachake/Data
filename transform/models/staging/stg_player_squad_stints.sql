select
    player_name,
    wiki_title,
    team_id,
    nullif(club_raw, '') as club_raw,
    season,
    position,
    shirt_no,
    appearances,
    goals,
    source_url
from {{ source('staging', 'player_squad_stints') }}
