-- ERROR level test
-- Every match must have two different teams.
-- Returns rows when home_team_id = away_team_id (should be zero rows to pass).

select
    match_id,
    season_id,
    home_team_id,
    away_team_id
from {{ ref('match') }}
where home_team_id = away_team_id
