{{
  config(
    materialized='table',
    tags=['mart']
  )
}}

/*
  player_percentiles — within-league and continental percentile ranks
  per position and season.

  Only computed for players with ≥ 450 minutes (5 * 90) in the season.
  Positions are grouped into broad buckets for sample-size stability.
*/

with base as (
    select
        player_id,
        season_id,
        league_id,
        season,
        position,
        minutes_played,
        goals_per90,
        minutes_share,
        data_tier
    from {{ ref('player_season') }}
    where minutes_played >= 450
      and position is not null
),

position_bucket as (
    select
        *,
        {{ position_bucket('position') }}            as pos_bucket
    from base
),

league_pct as (
    select
        *,
        percent_rank() over (
            partition by season_id, pos_bucket
            order by coalesce(goals_per90, 0)
        ) * 100                                     as goals_per90_pct_league,
        percent_rank() over (
            partition by season_id, pos_bucket
            order by coalesce(minutes_share, 0)
        ) * 100                                     as minutes_share_pct_league
    from position_bucket
),

continental_pct as (
    select
        player_id,
        season,
        pos_bucket,
        percent_rank() over (
            partition by season, pos_bucket
            order by coalesce(goals_per90, 0)
        ) * 100                                     as goals_per90_pct_continental,
        percent_rank() over (
            partition by season, pos_bucket
            order by coalesce(minutes_share, 0)
        ) * 100                                     as minutes_share_pct_continental
    from position_bucket
)

select
    lp.player_id,
    lp.season_id,
    lp.league_id,
    lp.season,
    lp.pos_bucket,
    lp.minutes_played,
    lp.goals_per90,
    lp.minutes_share,
    round(lp.goals_per90_pct_league::numeric, 1)            as goals_per90_pct_league,
    round(lp.minutes_share_pct_league::numeric, 1)          as minutes_share_pct_league,
    round(cp.goals_per90_pct_continental::numeric, 1)       as goals_per90_pct_continental,
    round(cp.minutes_share_pct_continental::numeric, 1)     as minutes_share_pct_continental,
    lp.data_tier
from league_pct lp
left join continental_pct cp
    on  cp.player_id  = lp.player_id
    and cp.season     = lp.season
    and cp.pos_bucket = lp.pos_bucket
