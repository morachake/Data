{{
  config(
    materialized='table',
    tags=['mart']
  )
}}

/*
  shortlist — filterable scout view.

  One wide row per (player, season) with every available stat:
    identity / bio, playing time, output, discipline, talent components,
    percentiles, year-over-year progression, career totals, injuries, GK.
*/

with players as (
    select
        pl.player_id,
        pl.full_name,
        pl.known_as,
        pl.nationality,
        pl.date_of_birth,
        pl.dob_confidence,
        pl.position,
        pl.current_club_raw,
        pl.place_of_birth,
        pl.height_cm,
        pl.image_url,
        pl.wikidata_id
    from {{ ref('player') }} pl
),

scores as (
    select distinct on (ts.player_id, ts.season_id)
        ts.player_id,
        ts.season_id,
        ts.league_id,
        ts.season,
        ts.age_at_midpoint,
        ts.data_tier,
        ts.talent_score,
        ts.comp_minutes_share,
        ts.comp_output_per90,
        ts.comp_position_pct,
        ts.comp_age_factor,
        ts.comp_progression,
        ts.comp_league_strength
    from {{ ref('talent_score') }} ts
    order by ts.player_id, ts.season_id, ts.talent_score desc nulls last
),

season_stats as (
    select distinct on (ps.player_id, ps.season_id)
        ps.player_id,
        ps.season_id,
        ps.appearances,
        ps.starts,
        ps.minutes_played,
        ps.goals,
        ps.own_goals,
        ps.goals_per90,
        ps.minutes_share,
        ps.starts_share
    from {{ ref('player_season') }} ps
    order by ps.player_id, ps.season_id, ps.minutes_played desc nulls last
),

current_club as (
    select distinct on (player_id)
        player_id,
        team_id,
        spell_id
    from {{ ref('player_club_spell') }}
    order by player_id, start_season desc nulls last, spell_id desc
),

team_names as (
    select team_id, name as team_name, competition_id
    from {{ ref('team') }}
),

competition_info as (
    select competition_id, name as league_name
    from {{ ref('competition') }}
),

-- Wikipedia league-table stats (leaders only — sparse). Normalise en-dash seasons.
wiki_stats as (
    select
        p.player_id,
        replace(replace(s.season, '–', '-'), '—', '-') as season,
        sum(s.stat_value) filter (where s.stat_type = 'assists')      as assists,
        sum(s.stat_value) filter (where s.stat_type = 'yellow_cards') as yellow_cards,
        sum(s.stat_value) filter (where s.stat_type = 'red_cards')    as red_cards,
        sum(s.stat_value) filter (where s.stat_type = 'clean_sheets') as wiki_clean_sheets
    from {{ ref('fct_psl_player_stats') }} s
    join {{ ref('player') }} p
      on nullif(trim(s.player_name), '') is not null
     and (
            lower(p.full_name) = lower(s.player_name)
         or (
                nullif(trim(p.known_as), '') is not null
            and lower(p.known_as) = lower(s.player_name)
         )
     )
    group by p.player_id, replace(replace(s.season, '–', '-'), '—', '-')
),

career_totals as (
    select
        player_id,
        sum(appearances)           as career_appearances,
        sum(goals)                 as career_goals,
        count(distinct club_raw)   as career_clubs
    from {{ ref('fct_player_career') }}
    group by player_id
),

injury_counts as (
    select player_id, count(*) as injury_notes
    from {{ ref('fct_player_injuries') }}
    group by player_id
)

select
    pl.player_id,
    pl.full_name,
    pl.known_as,
    pl.nationality,
    pl.date_of_birth,
    pl.dob_confidence,
    pl.place_of_birth,
    pl.height_cm,
    pl.image_url,
    pl.wikidata_id,
    pl.position,
    {{ position_bucket('pl.position') }}              as position_bucket,
    s.season_id,
    s.league_id,
    s.season,
    ci.league_name,
    coalesce(gk.age, s.age_at_midpoint)               as age_at_midpoint,
    s.data_tier,
    case
        when {{ position_bucket('pl.position') }} = 'GK'
            then coalesce(gk.gk_talent_score, s.talent_score)
        else s.talent_score
    end                                               as talent_score,
    s.comp_minutes_share,
    s.comp_output_per90,
    s.comp_position_pct,
    s.comp_age_factor,
    s.comp_progression,
    s.comp_league_strength,
    st.appearances,
    st.starts,
    st.minutes_played,
    st.goals,
    st.own_goals,
    st.goals_per90,
    st.minutes_share,
    st.starts_share,
    ws.assists,
    case
        when st.minutes_played >= 45 and ws.assists is not null
            then round(ws.assists * 90.0 / st.minutes_played, 2)
    end                                               as assists_per90,
    ws.yellow_cards,
    ws.red_cards,
    coalesce(gk.clean_sheets, ws.wiki_clean_sheets)   as clean_sheets,
    pp.goals_per90_pct_league,
    pp.minutes_share_pct_league,
    pp.goals_per90_pct_continental,
    pp.minutes_share_pct_continental,
    prog.prev_minutes_share,
    prog.prev_goals_per90,
    prog.minutes_share_delta,
    prog.goals_per90_delta,
    ct.career_appearances,
    ct.career_goals,
    ct.career_clubs,
    case
        when ct.career_appearances > 0
            then round(ct.career_goals::numeric / ct.career_appearances, 2)
    end                                               as career_goals_per_app,
    coalesce(ic.injury_notes, 0)                      as injury_notes,
    gk.conceded_p90,
    gk.expected_p90,
    gk.goals_prevented_p90,
    gk.clean_sheet_rate,
    gk.gk_talent_score,
    gk.sample_confidence                              as gk_sample_confidence,
    gk.conceded                                       as gk_conceded,
    gk.expected                                       as gk_expected,
    gk.age_band                                       as gk_age_band,
    gk.pct_minutes_share                              as gk_pct_minutes_share,
    gk.pct_goals_prevented                            as gk_pct_goals_prevented,
    gk.pct_clean_sheets                               as gk_pct_clean_sheets,
    cc.team_id                                        as current_team_id,
    coalesce(tn.team_name, pl.current_club_raw)       as current_team_name
from players pl
join scores s           using (player_id)
left join season_stats st
    on  st.player_id = s.player_id
    and st.season_id = s.season_id
left join current_club cc on cc.player_id = pl.player_id
left join team_names tn   on tn.team_id  = cc.team_id
left join (
    select distinct on (player_id, season_id) *
    from {{ ref('gk_season') }}
    order by player_id, season_id, minutes desc nulls last
) gk
    on  gk.player_id = s.player_id
    and gk.season_id = s.season_id
left join (
    select distinct on (player_id, season_id) *
    from {{ ref('player_percentiles') }}
    order by player_id, season_id, minutes_played desc nulls last
) pp
    on  pp.player_id = s.player_id
    and pp.season_id = s.season_id
left join (
    select distinct on (player_id, current_season_id) *
    from {{ ref('player_progression') }}
    order by player_id, current_season_id
) prog
    on  prog.player_id         = s.player_id
    and prog.current_season_id = s.season_id
left join wiki_stats ws
    on  ws.player_id = pl.player_id
    and ws.season    = replace(replace(s.season, '–', '-'), '—', '-')
left join career_totals ct on ct.player_id = pl.player_id
left join injury_counts ic on ic.player_id = pl.player_id
left join competition_info ci
    on  ci.competition_id = s.league_id
