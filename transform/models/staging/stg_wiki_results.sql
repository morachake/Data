select
    season,
    trim(home_team_raw) as home_team_raw,
    trim(away_team_raw) as away_team_raw,
    home_goals,
    away_goals,
    source_url
from {{ source('staging', 'wiki_results') }}
