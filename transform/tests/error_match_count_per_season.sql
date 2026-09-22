-- ERROR level test
-- Match count per season must be >= 50% of the expected count.
-- (A complete season of 16 teams has 16*15=240 matches.)
-- Returns (season_id, actual_count, expected_count) rows that are too low.

with season_counts as (
    select
        s.season_id,
        s.competition_id,
        s.season_label,
        s.expected_teams,
        coalesce(s.expected_teams * (s.expected_teams - 1), 0) as expected_matches,
        count(m.match_id)                                       as actual_matches
    from {{ ref('season') }} s
    left join {{ ref('match') }} m on m.season_id = s.season_id
    group by
        s.season_id, s.competition_id, s.season_label,
        s.expected_teams
)

-- For each competition, the most recent season may be ongoing and therefore
-- legitimately below 50%.  Exclude it from the error check.
, latest_per_competition as (
    select distinct on (competition_id)
        season_id
    from season_counts
    order by competition_id, season_label desc
)

select
    season_id,
    competition_id,
    season_label,
    actual_matches,
    expected_matches
from season_counts
where
    expected_matches > 0
    and actual_matches < expected_matches * 0.5
    -- exclude seasons with no data at all (not yet scraped)
    and actual_matches > 0
    -- exclude the most recent season per competition (may be ongoing)
    and season_id not in (select season_id from latest_per_competition)
