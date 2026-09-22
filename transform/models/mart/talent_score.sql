{{
  config(
    materialized='table',
    tags=['mart']
  )
}}

/*
  talent_score — transparent weighted blend per §7.13 of the architecture.

  Weights are read from seeds/talent_weights.csv.
  Tier A and Tier B players use different weights (see the seed).

  Components:
    minutes_share     — involvement (how much they play)
    output_per90      — productivity (goals+assists per 90)
    position_percentile — within-league rank for their position
    age_factor        — 1 – (age - 17) / (27 - 17) capped at [0,1]: younger = higher
    progression_delta — YoY improvement in minutes_share
    league_strength   — difficulty adjustment

  score = sum(component_value * weight) / sum(weights)
  Final score is normalised to [0, 100].
*/

with weights as (
    select
        component,
        tier_a_weight::numeric  as wa,
        tier_b_weight::numeric  as wb
    from {{ ref('talent_weights') }}
),

players as (
    select
        ps.player_id,
        ps.season_id,
        ps.league_id,
        ps.season,
        ps.age_at_midpoint,
        ps.minutes_share,
        ps.goals_per90,
        ps.data_tier,
        ps.position,
        -- GKs are ranked by playing-time share (they never score goals).
        -- All other positions use goal-output percentile.
        case
            when ps.position = 'GK'
            then coalesce(pp.minutes_share_pct_league, 50)
            else coalesce(pp.goals_per90_pct_league, 50)
        end                                         as position_percentile,
        pp.minutes_share_pct_league,
        prog.minutes_share_delta,
        ls.strength_index
    from {{ ref('player_season') }} ps
    left join {{ ref('player_percentiles') }} pp
        on  pp.player_id  = ps.player_id
        and pp.season_id  = ps.season_id
    left join {{ ref('player_progression') }} prog
        on  prog.player_id         = ps.player_id
        and prog.current_season_id = ps.season_id
    left join {{ ref('league_strength') }} ls
        on  ls.competition_id = ps.league_id
    where ps.minutes_played >= 270   -- minimum 3 full games
),

components as (
    select
        p.*,
        -- Each component bounded [0, 100] so the weighted average stays in range.
        -- minutes_share: fraction of total season minutes the player played (%)
        least(greatest(coalesce(p.minutes_share, 0), 0), 100)       as c_minutes_share,
        -- output_per90: 0.5 goals/90 → 50; 1.0+ → capped at 100
        least(greatest(coalesce(p.goals_per90 * 100, 0), 0), 100)   as c_output_per90,
        -- position_percentile already coalesced to 50 in the players CTE above
        least(greatest(p.position_percentile, 0), 100)              as c_position_pct,
        -- Age factor: peaks at 21, declines after 27; 50 when age unknown
        greatest(0, least(100,
            case when p.age_at_midpoint is null then 50
                 when p.age_at_midpoint <= 21 then 100
                 when p.age_at_midpoint >= 27 then 10
                 else 100 - ((p.age_at_midpoint - 21) * 15)
            end
        ))                                                          as c_age_factor,
        -- progression: YoY change in minutes share, capped [0, 100]
        least(greatest(coalesce(p.minutes_share_delta * 100, 0), 0), 100) as c_progression,
        -- league_strength [0, 100] (strength_index is [0,1])
        least(greatest(coalesce(p.strength_index * 100, 50), 0), 100) as c_league_strength,
        -- Tier flag
        case when p.data_tier = 'A' then 'a' else 'b' end          as weight_tier
    from players p
),

scored as (
    select
        c.*,
        -- Tier A weights
        (c.c_minutes_share    * (select wa from weights where component='minutes_share') +
         c.c_output_per90     * (select wa from weights where component='output_per90') +
         c.c_position_pct     * (select wa from weights where component='position_percentile') +
         c.c_age_factor       * (select wa from weights where component='age_factor') +
         c.c_progression      * (select wa from weights where component='progression_delta') +
         c.c_league_strength  * (select wa from weights where component='league_strength')
        ) / (
            (select wa from weights where component='minutes_share') +
            (select wa from weights where component='output_per90') +
            (select wa from weights where component='position_percentile') +
            (select wa from weights where component='age_factor') +
            (select wa from weights where component='progression_delta') +
            (select wa from weights where component='league_strength')
        )                                                           as score_a,
        -- Tier B weights
        (c.c_minutes_share    * (select wb from weights where component='minutes_share') +
         c.c_output_per90     * (select wb from weights where component='output_per90') +
         c.c_position_pct     * (select wb from weights where component='position_percentile') +
         c.c_age_factor       * (select wb from weights where component='age_factor') +
         c.c_progression      * (select wb from weights where component='progression_delta') +
         c.c_league_strength  * (select wb from weights where component='league_strength')
        ) / (
            (select wb from weights where component='minutes_share') +
            (select wb from weights where component='output_per90') +
            (select wb from weights where component='position_percentile') +
            (select wb from weights where component='age_factor') +
            (select wb from weights where component='progression_delta') +
            (select wb from weights where component='league_strength')
        )                                                           as score_b
    from components c
)

select
    player_id,
    season_id,
    league_id,
    season,
    age_at_midpoint,
    data_tier,
    round(case when weight_tier = 'a' then score_a else score_b end, 1) as talent_score,
    round(c_minutes_share, 1)     as comp_minutes_share,
    round(c_output_per90, 1)      as comp_output_per90,
    round(c_position_pct, 1)      as comp_position_pct,
    round(c_age_factor, 1)        as comp_age_factor,
    round(c_progression, 1)       as comp_progression,
    round(c_league_strength, 1)   as comp_league_strength
from scored
