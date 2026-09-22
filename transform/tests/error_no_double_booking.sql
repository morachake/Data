-- ERROR level test
-- No team may play twice on the same date in the same competition.
-- Returns offending (season_id, team_id, match_date, count) rows.

with team_match_dates as (
    select
        season_id,
        match_date,
        home_team_id as team_id
    from {{ ref('match') }}
    where match_date is not null

    union all

    select
        season_id,
        match_date,
        away_team_id
    from {{ ref('match') }}
    where match_date is not null
)

select
    season_id,
    team_id,
    match_date,
    count(*) as matches_on_day
from team_match_dates
group by season_id, team_id, match_date
having count(*) > 1
