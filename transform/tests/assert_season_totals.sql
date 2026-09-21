with actual as (
    select season, count(*) as matches, sum(home_goals + away_goals) as goals
    from {{ ref('fct_matches') }}
    group by season
)
select c.season, c.expected_matches, a.matches, c.expected_goals, a.goals
from {{ ref('season_checks') }} c
left join actual a using (season)
where (c.expected_matches <> 0 and a.matches is distinct from c.expected_matches)
   or (c.expected_goals <> 0 and a.goals is distinct from c.expected_goals)
