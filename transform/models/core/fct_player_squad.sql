select
    s.player_name,
    s.wiki_title,
    s.team_id,
    t.team_name,
    s.club_raw,
    s.season,
    s.position,
    s.shirt_no,
    s.appearances,
    s.goals,
    s.source_url
from {{ ref('stg_player_squad_stints') }} s
left join {{ ref('teams') }} t on t.team_id = s.team_id
