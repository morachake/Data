select
    c.player_id,
    p.full_name,
    c.years,
    c.club_raw,
    a.team_id,
    c.appearances,
    c.goals,
    c.source_url
from {{ ref('stg_player_career') }} c
join {{ ref('stg_players') }} p on p.player_id = c.player_id
left join {{ ref('team_alias') }} a
    on a.source_id = 'wikipedia_season'
   and lower(a.alias) = lower(c.club_raw)
