-- ERROR level test
-- Within a single season, the same fixture (home + away) may only appear once
-- in the reconciled match table.
-- Returns duplicate (season_id, home_team_id, away_team_id) tuples.

select
    season_id,
    home_team_id,
    away_team_id,
    count(*) as match_count
from {{ ref('match') }}
group by season_id, home_team_id, away_team_id
having count(*) > 1
