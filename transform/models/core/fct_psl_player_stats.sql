select
    s.player_name,
    s.season,
    s.club_raw,
    s.stat_type,
    s.stat_value,
    s.source_url,
    s.league_id
from {{ ref('stg_player_season_stats') }} s
