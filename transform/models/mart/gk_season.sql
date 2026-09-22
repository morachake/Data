{{
  config(
    materialized='table',
    tags=['mart']
  )
}}

/*
  Goalkeeper season profile and GK-specific talent score.
  Percentiles are pooled across ALL leagues for the same season label and
  age band, because a single league rarely has enough young keepers to
  rank fairly.

  Lineup path uses gk_match (Tier A). Until appearances resolve player_id,
  Wikipedia squad/career minutes plus team goals-against are used.
*/

{% set min_minutes = 270 %}
{% set shrink_minutes = 1800 %}

with lineup as (
    select
        season_id,
        player_id,
        team_id,
        count(*)                        as apps,
        sum(started::int)               as starts,
        sum(minutes_played)             as minutes,
        sum(goals_conceded_on_pitch)    as conceded,
        sum(expected_conceded_on_pitch) as expected,
        sum(clean_sheet::int)           as clean_sheets
    from {{ ref('gk_match') }}
    group by season_id, player_id, team_id
),

team_minutes as (
    select season_id, team_id, count(*) * 90 as team_minutes
    from {{ ref('gk_expected_conceded') }}
    group by season_id, team_id
),

team_expected as (
    select season_id, team_id, sum(expected_conceded) as expected
    from {{ ref('gk_expected_conceded') }}
    group by season_id, team_id
),

squad_team as (
    select distinct on (pl.player_id, s.season)
        pl.player_id,
        s.season,
        s.team_id
    from {{ ref('fct_player_squad') }} s
    join {{ ref('player') }} pl
      on lower(pl.full_name) = lower(s.player_name)
      or (s.wiki_title is not null and lower(pl.known_as) = lower(s.wiki_title))
    where s.team_id is not null
    order by pl.player_id, s.season, coalesce(s.appearances, 0) desc
),

wiki as (
    select
        ps.season_id,
        ps.player_id,
        coalesce(st.team_id, cc.team_id)                              as team_id,
        ps.appearances                                                as apps,
        ps.starts,
        ps.minutes_played                                             as minutes,
        sta.goals_against
            * ps.minutes_played
            / nullif(tm.team_minutes, 0)                              as conceded,
        te.expected
            * ps.minutes_played
            / nullif(tm.team_minutes, 0)                              as expected,
        0::bigint                                                     as clean_sheets
    from {{ ref('player_season') }} ps
    join {{ ref('player') }} p using (player_id)
    left join squad_team st
           on st.player_id = ps.player_id
          and (st.season = ps.season or st.season = 'current')
    left join (
        select distinct on (player_id)
            player_id, team_id
        from {{ ref('player_club_spell') }}
        order by player_id, start_season desc nulls last, spell_id desc
    ) cc on cc.player_id = ps.player_id
    left join team_minutes tm
           on tm.season_id = ps.season_id
          and tm.team_id   = coalesce(st.team_id, cc.team_id)
    left join team_expected te
           on te.season_id = ps.season_id
          and te.team_id   = coalesce(st.team_id, cc.team_id)
    left join {{ ref('standings') }} sta
           on sta.season_id = ps.season_id
          and sta.team_id   = coalesce(st.team_id, cc.team_id)
    where {{ position_bucket('p.position') }} = 'GK'
      and not exists (
          select 1 from lineup l
          where l.player_id = ps.player_id
            and l.season_id = ps.season_id
      )
),

s as (
    select * from lineup
    union all
    select * from wiki
),

enriched as (
    select
        s.*,
        se.season_label,
        se.competition_id,
        cov.tier,
        p.full_name                                                   as display_name,
        p.dob_confidence,
        ls.strength_index                                             as strength_norm,
        s.minutes::numeric / nullif(tm.team_minutes, 0)               as minutes_share,
        90.0 * s.conceded / nullif(s.minutes, 0)                      as conceded_p90,
        90.0 * s.expected / nullif(s.minutes, 0)                      as expected_p90,
        90.0 * (coalesce(s.expected, 0) - coalesce(s.conceded, 0))
            / nullif(s.minutes, 0)
            * s.minutes / (s.minutes + {{ shrink_minutes }}.0)        as goals_prevented_p90,
        s.clean_sheets::numeric / nullif(s.starts, 0)                 as clean_sheet_rate,
        case
            when p.date_of_birth is not null and se.season_label ~ '\d{4}'
            then date_part('year', age(
                make_date((substring(se.season_label from '\d{4}'))::int + 1, 1, 1),
                p.date_of_birth
            ))::int
            else null
        end                                                           as age
    from s
    join {{ ref('player') }} p using (player_id)
    join {{ ref('season') }} se using (season_id)
    left join team_minutes tm using (season_id, team_id)
    left join {{ ref('league_season_coverage') }} cov using (season_id)
    left join {{ ref('league_strength') }} ls
           on ls.competition_id = se.competition_id
),

eligible as (
    select *,
           case when age is null then 'unknown'
                when age < 21 then 'U21'
                when age <= 24 then 'U24'
                else '25+' end as age_band
    from enriched
    where minutes >= {{ min_minutes }}
),

ranked as (
    select *,
           percent_rank() over (partition by season_label, age_band
                                order by coalesce(minutes_share, 0))   as pct_minutes_share,
           percent_rank() over (partition by season_label
                                order by coalesce(goals_prevented_p90, 0))
                                                                      as pct_goals_prevented,
           percent_rank() over (partition by season_label
                                order by coalesce(clean_sheet_rate, 0))
                                                                      as pct_clean_sheets
    from eligible
)

select
    player_id,
    season_id,
    team_id,
    competition_id,
    season_label,
    display_name,
    dob_confidence,
    age,
    age_band,
    tier,
    apps,
    starts,
    minutes,
    conceded,
    expected,
    clean_sheets,
    minutes_share,
    conceded_p90,
    expected_p90,
    goals_prevented_p90,
    clean_sheet_rate,
    strength_norm,
    pct_minutes_share,
    pct_goals_prevented,
    pct_clean_sheets,
    round(100 * (
          0.40 * pct_minutes_share
        + 0.30 * pct_goals_prevented
        + 0.15 * pct_clean_sheets
        + 0.15 * coalesce(strength_norm, 0.5)
    )::numeric, 1) as gk_talent_score,
    case when minutes < 1350 then 'low'
         when minutes < 2700 then 'medium'
         else 'high' end as sample_confidence
from ranked
