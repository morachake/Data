with r as (select * from {{ ref('stg_wiki_results') }}),
a as (select * from {{ ref('team_aliases') }} where source = 'wikipedia')

select
    md5(r.season || ha.team_id || aa.team_id) as match_id,
    r.season,
    ha.team_id as home_team_id,
    aa.team_id as away_team_id,
    r.home_goals,
    r.away_goals,
    case when r.home_goals > r.away_goals then 'H'
         when r.home_goals < r.away_goals then 'A'
         else 'D' end as result,
    'wikipedia' as source,
    r.source_url
from r
left join a ha on ha.alias = r.home_team_raw
left join a aa on aa.alias = r.away_team_raw
