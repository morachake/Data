select
    player_name,
    season,
    nullif(club_raw, '') as club_raw,
    stat_type,
    stat_value,
    source_url,
    league_id
from {{ source('staging', 'player_season_stats') }}
