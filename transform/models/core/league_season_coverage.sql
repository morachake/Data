{{
  config(
    materialized='table',
    tags=['core', 'partitioned']
  )
}}

/*
  league_season_coverage — computes data completeness metrics and assigns
  a coverage tier (A/B/C) per §7.9 of the architecture.

  Tier thresholds:
    A: ≥95% matches with result + ≥80% goals with scorer + ≥70% matches with lineups
       + ≥60% players with DOB
    B: ≥90% matches with result + ≥50% goals with scorer
    C: ≥70% matches with result
    (below C = no tier assigned)
*/

with seasons as (
    select season_id, competition_id, season_label, expected_teams
    from {{ ref('season') }}
),

match_counts as (
    select
        season_id,
        count(*)                                                        as total_matches,
        count(case when status = 'played' then 1 end)                  as matches_with_result
    from {{ ref('match') }}
    group by season_id
),

expected_counts as (
    select
        s.season_id,
        case
            when s.expected_teams is not null
                then s.expected_teams * (s.expected_teams - 1)
            else null
        end as expected_matches
    from seasons s
),

goal_counts as (
    select
        m.season_id,
        count(g.goal_id)                                                as total_goals,
        count(case when g.player_id is not null then g.goal_id end)     as goals_with_scorer
    from {{ ref('match') }} m
    left join {{ ref('goal') }} g using (match_id)
    group by m.season_id
),

lineup_counts as (
    select
        m.season_id,
        count(distinct a.match_id)                                      as matches_with_lineups
    from {{ ref('match') }} m
    left join {{ ref('appearance') }} a using (match_id)
    group by m.season_id
),

player_dob_counts as (
    -- Fraction of distinct players seen in this season who have a DOB
    select
        m.season_id,
        count(distinct a.player_id)                                     as total_players,
        count(distinct case when p.date_of_birth is not null
                            then a.player_id end)                       as players_with_dob
    from {{ ref('appearance') }} a
    join {{ ref('match') }} m using (match_id)
    left join {{ ref('player') }} p on p.player_id = a.player_id
    group by m.season_id
),

combined as (
    select
        s.season_id,
        mc.total_matches,
        mc.matches_with_result,
        ec.expected_matches,
        round(100.0 * mc.matches_with_result / nullif(mc.total_matches, 0), 2)
            as pct_matches_with_result,
        round(100.0 * gc.goals_with_scorer / nullif(gc.total_goals, 0), 2)
            as pct_goals_with_scorer,
        round(100.0 * lc.matches_with_lineups / nullif(mc.total_matches, 0), 2)
            as pct_matches_with_lineups,
        round(100.0 * pd.players_with_dob / nullif(pd.total_players, 0), 2)
            as pct_players_with_dob
    from seasons s
    left join match_counts  mc using (season_id)
    left join expected_counts ec using (season_id)
    left join goal_counts   gc using (season_id)
    left join lineup_counts lc using (season_id)
    left join player_dob_counts pd using (season_id)
)

select
    season_id,
    pct_matches_with_result,
    pct_goals_with_scorer,
    pct_matches_with_lineups,
    pct_players_with_dob,
    case
        when pct_matches_with_result >= 95
         and coalesce(pct_goals_with_scorer,  0) >= 80
         and coalesce(pct_matches_with_lineups, 0) >= 70
         and coalesce(pct_players_with_dob,   0) >= 60
        then 'A'
        when pct_matches_with_result >= 90
         and coalesce(pct_goals_with_scorer, 0) >= 50
        then 'B'
        when pct_matches_with_result >= 70
        then 'C'
        else null
    end as tier,
    now() as computed_at
from combined
