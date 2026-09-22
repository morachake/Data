{{
  config(
    materialized='table',
    tags=['mart']
  )
}}

/*
  player_progression — year-over-year change in key metrics.
  Used in talent_score to reward improving players.
*/

with ps as (
    select
        player_id,
        league_id,
        season,
        season_id,
        minutes_share,
        goals_per90,
        age_at_midpoint
    from {{ ref('player_season') }}
),

lagged as (
    select
        curr.player_id,
        curr.season_id                                              as current_season_id,
        curr.league_id,
        curr.season,
        curr.age_at_midpoint,
        curr.minutes_share,
        curr.goals_per90,
        prev.minutes_share                                         as prev_minutes_share,
        prev.goals_per90                                           as prev_goals_per90,
        -- delta: positive = improved
        curr.minutes_share - prev.minutes_share                    as minutes_share_delta,
        coalesce(curr.goals_per90, 0) - coalesce(prev.goals_per90, 0)
                                                                   as goals_per90_delta
    from ps curr
    join ps prev
        on  prev.player_id  = curr.player_id
        -- Pair seasons within the same league separated by 1 year
        -- Season labels are "YYYY-YY"; compare start years
        and prev.league_id  = curr.league_id
        and (substring(prev.season from '\d{4}'))::int + 1 =
            (substring(curr.season from '\d{4}'))::int
)

select * from lagged
