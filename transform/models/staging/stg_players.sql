select
    player_id,
    wiki_title,
    full_name,
    date_of_birth,
    place_of_birth,
    height,
    position,
    current_club,
    nationality,
    wikidata_id,
    image_url,
    bio,
    source_url
from {{ source('staging', 'players') }}
