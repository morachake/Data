{{ config(severity='warn') }}
-- WARN level test (severity: warn)
-- Players without a date of birth cannot be age-filtered in talent discovery.
-- Returns players with dob_confidence = 'unknown' as a fraction per season.

with season_player_dob as (
    select
        m.season_id,
        count(distinct a.player_id)                                         as total_players,
        count(distinct case
            when p.dob_confidence = 'unknown' or p.player_id is null
            then a.player_id end)                                           as players_unknown_dob
    from {{ ref('appearance') }} a
    join {{ ref('match') }} m using (match_id)
    left join {{ ref('player') }} p on p.player_id = a.player_id
    group by m.season_id
    having count(distinct a.player_id) > 0
)

select
    season_id,
    total_players,
    players_unknown_dob,
    round(100.0 * players_unknown_dob / nullif(total_players, 0), 1)    as pct_unknown_dob
from season_player_dob
where round(100.0 * players_unknown_dob / nullif(total_players, 0), 1) > 40
