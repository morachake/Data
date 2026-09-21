with m as (select * from {{ ref('fct_matches') }}),
rows as (
    select season, home_team_id as team_id, home_goals as gf, away_goals as ga,
           case result when 'H' then 3 when 'D' then 1 else 0 end as pts,
           (result = 'H')::int as w, (result = 'D')::int as d, (result = 'A')::int as l
    from m
    union all
    select season, away_team_id, away_goals, home_goals,
           case result when 'A' then 3 when 'D' then 1 else 0 end,
           (result = 'A')::int, (result = 'D')::int, (result = 'H')::int
    from m
)
select
    season, team_id,
    count(*) as played, sum(w) as won, sum(d) as drawn, sum(l) as lost,
    sum(gf) as goals_for, sum(ga) as goals_against, sum(gf) - sum(ga) as goal_diff,
    sum(pts) as points,
    rank() over (partition by season order by sum(pts) desc, sum(gf) - sum(ga) desc, sum(gf) desc) as position
from rows
group by season, team_id
