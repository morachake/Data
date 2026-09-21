select
    player_id,
    detail,
    source_url
from {{ source('staging', 'player_injuries') }}
