{{
  config(
    materialized='table',
    tags=['mart']
  )
}}

/*
  player_career_path — ordered list of club stints per player across all leagues.
  One row per (player, club, season).

  Ordered by season label (assumes "YYYY-YY" format).
  Used for career context in the shortlist dashboard and backtest models.
*/

with spells as (
    select
        ps.player_id,
        ps.team_id,
        t.name                                                          as team_name,
        ps.competition_id,
        coalesce(ps.start_season, ps.spell_id)                         as season_label,
        ps.loan,
        ps.source_id,
        row_number() over (
            partition by ps.player_id
            order by ps.start_season nulls last, ps.spell_id
        )                                                               as career_order
    from {{ ref('player_club_spell') }} ps
    left join {{ ref('team') }} t using (team_id)
),

with_stats as (
    select
        s.*,
        ps.appearances,
        ps.starts,
        ps.minutes_played,
        ps.goals,
        ps.age_at_midpoint,
        ps.data_tier
    from spells s
    left join {{ ref('player_season') }} ps
        on  ps.player_id = s.player_id
        and ps.season    = s.season_label
)

select * from with_stats
