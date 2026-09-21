with p as (select * from {{ ref('stg_players') }}),
current_season as (
    select max(season) as season from {{ ref('standings') }}
),
current_clubs as (
    select distinct t.team_name
    from {{ ref('standings') }} s
    join {{ ref('teams') }} t on t.team_id = s.team_id
    join current_season c on c.season = s.season
),
current_squad as (
    select distinct lower(player_name) as name, lower(wiki_title) as wiki_title
    from {{ ref('stg_player_squad_stints') }}
    where season = 'current'
)

select
    p.player_id,
    p.wiki_title,
    p.full_name,
    p.date_of_birth,
    p.place_of_birth,
    p.height,
    p.position,
    p.current_club,
    p.nationality,
    p.wikidata_id,
    p.image_url,
    p.bio,
    p.source_url,
    case
        when exists (
            select 1 from current_clubs cc
            where p.current_club ilike '%' || cc.team_name || '%'
        ) then 'in_league'
        when exists (
            select 1 from current_squad cs
            where cs.name = lower(p.full_name)
               or cs.wiki_title = lower(p.wiki_title)
        ) then 'in_league'
        else 'left_league'
    end as league_status
from p
