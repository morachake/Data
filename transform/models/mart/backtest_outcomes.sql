{{
  config(
    materialized='table',
    tags=['mart']
  )
}}

/*
  backtest_outcomes — measures the predictive hit-rate of the talent_score model.

  Definition of "success":
    A player who had talent_score ≥ 65 in season Y later:
      (a) moved to a higher-strength league in season Y+1 or Y+2, OR
      (b) received a senior international cap within 2 seasons, OR
      (c) moved to a European league within 2 seasons.

  Phase 4 bootstrapping: option (a) only — compares career_path entries
  to league_strength.  Options (b)/(c) require an external caps/transfers
  source (Phase 5+).

  Columns:
    outcome = 'moved_up' | 'no_move' | 'unknown'
    hit     = true/false (moved_up = true)
*/

with scored_seasons as (
    select
        player_id,
        season_id,
        league_id,
        season,
        talent_score,
        -- Start year of the season for comparison
        (substring(season from '\d{4}'))::int   as season_start_year
    from {{ ref('talent_score') }}
    where talent_score >= 65
),

future_clubs as (
    select
        cp.player_id,
        cp.season_label                         as future_season,
        (substring(cp.season_label from '\d{4}'))::int as future_year,
        ls.strength_index                       as future_league_strength,
        cp.competition_id                       as future_competition_id
    from {{ ref('player_career_path') }} cp
    left join {{ ref('league_strength') }} ls
        on  ls.competition_id = cp.competition_id
    where cp.competition_id is not null
),

base_league_strength as (
    select competition_id, strength_index
    from {{ ref('league_strength') }}
),

outcomes as (
    select
        ss.player_id,
        ss.season_id,
        ss.league_id,
        ss.season,
        ss.talent_score,
        bls.strength_index                      as base_strength,
        -- Any move to a higher-strength league within 2 seasons
        max(case
            when fc.future_year between ss.season_start_year + 1
                                    and ss.season_start_year + 2
             and fc.future_league_strength > bls.strength_index + 0.05
            then 1 else 0
        end)                                    as moved_to_stronger_league
    from scored_seasons ss
    left join base_league_strength bls
        on  bls.competition_id = ss.league_id
    left join future_clubs fc
        on  fc.player_id = ss.player_id
    group by
        ss.player_id, ss.season_id, ss.league_id,
        ss.season, ss.talent_score, bls.strength_index
)

select
    player_id,
    season_id,
    league_id,
    season,
    talent_score,
    base_strength,
    case
        when moved_to_stronger_league = 1 then 'moved_up'
        else 'no_move'
    end                                         as outcome,
    moved_to_stronger_league = 1                as hit
from outcomes
