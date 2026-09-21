select
    i.player_id,
    p.full_name,
    i.detail,
    i.source_url
from {{ ref('stg_player_injuries') }} i
join {{ ref('stg_players') }} p on p.player_id = i.player_id
