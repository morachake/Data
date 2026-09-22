{{
  config(
    materialized='table',
    tags=['mart', 'partitioned']
  )
}}

/*
  player_season — one row per player per season.

  Metrics availability by tier:
    Tier A:  all columns populated
    Tier B:  no lineup-dependent metrics (started, minutes_played) — uses estimates
    Tier C:  appearances count only (from squad or result data)

  age_at_midpoint: age in years at the season's approximate midpoint
  (Jan 1 for aug-may seasons).
*/

with lineup_apps as (
    select
        a.player_id,
        m.season_id,
        m.league_id,
        m.season,
        count(distinct a.match_id)                                      as appearances,
        count(distinct case when a.started then a.match_id end)         as starts,
        sum(coalesce(a.minutes_played, 0))                              as minutes_played,
        sum(case when a.started then 1 else 0 end)                      as lineup_count
    from {{ ref('appearance') }} a
    join {{ ref('match') }} m using (match_id)
    where a.player_id is not null
    group by a.player_id, m.season_id, m.league_id, m.season
),

latest_rsa as (
    select season_id, competition_id, season_label
    from {{ ref('season') }}
    where competition_id = 'RSA_PREM'
    order by season_label desc
    limit 1
),

-- Wikipedia squad tables until official lineups populate appearance.
wiki_squad as (
    select
        pl.player_id,
        'RSA_PREM_' || coalesce(nullif(s.season, 'current'), lr.season_label) as season_id,
        'RSA_PREM'::text                                                      as league_id,
        coalesce(nullif(s.season, 'current'), lr.season_label)                as season,
        1::bigint                                                             as appearances,
        0::bigint                                                             as starts,
        (greatest(coalesce(s.appearances, 5), 3) * 90)::bigint                as minutes_played,
        0::bigint                                                             as lineup_count
    from {{ ref('fct_player_squad') }} s
    join {{ ref('player') }} pl
      on lower(pl.full_name) = lower(s.player_name)
      or (s.wiki_title is not null and lower(pl.known_as) = lower(s.wiki_title))
    cross join latest_rsa lr
),

-- Career appearance totals for players not on a scraped squad table.
-- Uses the AVERAGE appearances per career stint (not sum) to estimate one season.
-- Capped at 38 * 90 = 3 420 minutes so the minutes_share stays ≤ 100 %.
wiki_career as (
    select
        c.player_id,
        lr.season_id,
        lr.competition_id                                                     as league_id,
        lr.season_label                                                       as season,
        greatest(round(avg(c.appearances::float))::bigint, 1)                as appearances,
        0::bigint                                                             as starts,
        least(
            greatest(round(avg(c.appearances::float))::bigint, 1) * 90,
            38 * 90                                                           -- cap at 1 full season
        )::bigint                                                             as minutes_played,
        0::bigint                                                             as lineup_count
    from {{ ref('fct_player_career') }} c
    cross join latest_rsa lr
    where c.appearances is not null
      and c.appearances > 0
    group by c.player_id, lr.season_id, lr.competition_id, lr.season_label
),

-- Wikipedia season-page leaderboards for every scraped league.
wiki_leaders as (
    select
        pl.player_id,
        s.league_id || '_' || replace(replace(s.season, '–', '-'), '—', '-') as season_id,
        s.league_id,
        replace(replace(s.season, '–', '-'), '—', '-')                      as season,
        coalesce(
            nullif(max(s.stat_value) filter (where s.stat_type = 'appearances'), 0),
            case when s.league_id in ('CAF_CL', 'CAF_CC') then 8 else 20 end
        )::bigint                                                           as appearances,
        0::bigint                                                           as starts,
        least(
            coalesce(
                nullif(max(s.stat_value) filter (where s.stat_type = 'appearances'), 0),
                case when s.league_id in ('CAF_CL', 'CAF_CC') then 8 else 20 end
            ) * 90,
            38 * 90
        )::bigint                                                           as minutes_played,
        0::bigint                                                           as lineup_count
    from {{ ref('fct_psl_player_stats') }} s
    join {{ ref('player') }} pl
      on lower(pl.full_name) = lower(s.player_name)
      or lower(pl.known_as)  = lower(s.player_name)
    where s.league_id is not null
    group by pl.player_id, s.league_id, s.season
),

wiki_leader_goals as (
    select
        pl.player_id,
        s.league_id || '_' || replace(replace(s.season, '–', '-'), '—', '-') as season_id,
        coalesce(max(s.stat_value) filter (where s.stat_type = 'goals'), 0)  as goals
    from {{ ref('fct_psl_player_stats') }} s
    join {{ ref('player') }} pl
      on lower(pl.full_name) = lower(s.player_name)
      or lower(pl.known_as)  = lower(s.player_name)
    where s.league_id is not null
    group by pl.player_id, s.league_id, s.season
),

apps as (
    select * from lineup_apps
    union all
    select * from wiki_squad ws
    where not exists (
        select 1 from lineup_apps a
        where a.player_id = ws.player_id and a.season_id = ws.season_id
    )
    union all
    select * from wiki_leaders wl
    where not exists (
        select 1 from lineup_apps a
        where a.player_id = wl.player_id and a.season_id = wl.season_id
    )
      and not exists (
        select 1 from wiki_squad ws
        where ws.player_id = wl.player_id and ws.season_id = wl.season_id
    )
    union all
    select * from wiki_career wc
    where not exists (
        select 1 from lineup_apps a where a.player_id = wc.player_id
    )
      and not exists (
        select 1 from wiki_squad ws where ws.player_id = wc.player_id
    )
      and not exists (
        select 1 from wiki_leaders wl where wl.player_id = wc.player_id
    )
),

goal_stats as (
    select
        g.player_id,
        m.season_id,
        count(*) filter (where not g.is_own_goal)                       as goals,
        count(*) filter (where g.is_own_goal)                           as own_goals
    from {{ ref('goal') }} g
    join {{ ref('match') }} m using (match_id)
    where g.player_id is not null
    group by g.player_id, m.season_id
),

total_match_minutes as (
    -- Total minutes available in the season (for minutes_share calc)
    select season_id, count(*) * 90                                     as season_minutes
    from {{ ref('match') }}
    where status = 'played'
    group by season_id
),

player_info as (
    select player_id, date_of_birth, position, dob_confidence
    from {{ ref('player') }}
),

coverage as (
    select season_id, tier
    from {{ ref('league_season_coverage') }}
),

career_goals as (
    select player_id, coalesce(sum(goals), 0) as goals
    from {{ ref('fct_player_career') }}
    group by player_id
)

select
    a.player_id,
    a.season_id,
    a.league_id,
    a.season,
    a.appearances,
    a.starts,
    a.minutes_played,
    coalesce(gs.goals, wlg.goals, cg.goals, 0)                          as goals,
    coalesce(gs.own_goals, 0)                                           as own_goals,
    -- per-90 rates (null when < 45 minutes to avoid noise)
    case when a.minutes_played >= 45
        then round(coalesce(gs.goals, wlg.goals, cg.goals, 0) * 90.0 / a.minutes_played, 2)
        else null
    end                                                                 as goals_per90,
    -- minutes share: what fraction of season minutes did this player play
    case when sm.season_minutes > 0
        then round(100.0 * a.minutes_played / sm.season_minutes, 2)
        else null
    end                                                                 as minutes_share,
    -- starts share
    case when a.appearances > 0
        then round(100.0 * a.starts / a.appearances, 1)
        else null
    end                                                                 as starts_share,
    pi.position,
    pi.dob_confidence,
    -- age at season midpoint (Jan 1 of the ending year)
    case
        when pi.date_of_birth is not null and a.season ~ '\d{4}'
        then date_part('year', age(
            make_date(
                (substring(a.season from '\d{4}'))::int + 1,
                1, 1
            ),
            pi.date_of_birth
        ))::int
        else null
    end                                                                 as age_at_midpoint,
    coalesce(cv.tier, 'C')                                              as data_tier
from apps a
left join goal_stats gs         using (player_id, season_id)
left join wiki_leader_goals wlg using (player_id, season_id)
left join career_goals cg       using (player_id)
left join total_match_minutes sm using (season_id)
left join player_info pi        using (player_id)
left join coverage cv           using (season_id)
