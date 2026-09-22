{{
  config(
    materialized='table',
    tags=['core', 'partitioned']
  )
}}

/*
  conflict_log — records every match field where two sources disagree.

  Phase 2: compares wikipedia_season vs rsssf_tables (and later psl_official).
  Source priority:  psl_official=1, wikipedia_season=2, rsssf_tables=3.
  The winning_source is the one with the lower priority number.

  Only match-level conflicts are logged here for Phase 2.  Goal and player
  conflicts follow in Phase 3+.
*/

with wiki as (
    select
        league_id,
        season,
        home_team_raw,
        away_team_raw,
        home_goals,
        away_goals,
        'wikipedia_season' as source_id
    from {{ ref('stg_match') }}
    where source_id = 'wikipedia_season'
),

rsssf as (
    select
        league_id,
        season,
        home_team_raw,
        away_team_raw,
        home_goals,
        away_goals,
        'rsssf_tables' as source_id
    from {{ ref('stg_match') }}
    where source_id = 'rsssf_tables'
),

-- Align on resolved team_ids so we can compare across different raw names
wiki_resolved as (
    select
        w.*,
        ha.team_id as home_team_id,
        aa.team_id as away_team_id
    from wiki w
    left join {{ ref('team_alias') }} ha
           on ha.alias = w.home_team_raw and ha.source_id = w.source_id
    left join {{ ref('team_alias') }} aa
           on aa.alias = w.away_team_raw and aa.source_id = w.source_id
    where ha.team_id is not null and aa.team_id is not null
),

rsssf_resolved as (
    select
        r.*,
        ha.team_id as home_team_id,
        aa.team_id as away_team_id
    from rsssf r
    left join {{ ref('team_alias') }} ha
           on ha.alias = r.home_team_raw and ha.source_id = r.source_id
    left join {{ ref('team_alias') }} aa
           on aa.alias = r.away_team_raw and aa.source_id = r.source_id
    where ha.team_id is not null and aa.team_id is not null
),

conflicts as (
    select
        'match'                                             as entity_type,
        w.league_id || '_' || w.season || '_'
            || w.home_team_id || '_' || w.away_team_id     as entity_id,
        'score'                                             as field,
        w.source_id                                        as source_a_id,
        w.home_goals::text || '-' || w.away_goals::text    as source_a_value,
        r.source_id                                        as source_b_id,
        r.home_goals::text || '-' || r.away_goals::text    as source_b_value,
        'wikipedia_season'                                  as winning_source,
        'source_priority: psl_official=1, wikipedia=2, rsssf=3'
            as resolution_rule
    from wiki_resolved w
    join rsssf_resolved r
        on  r.league_id    = w.league_id
        and r.season       = w.season
        and r.home_team_id = w.home_team_id
        and r.away_team_id = w.away_team_id
    where
        w.home_goals != r.home_goals
        or w.away_goals != r.away_goals
)

select
    row_number() over (order by entity_id, field)::text as conflict_id,
    entity_type,
    entity_id,
    field,
    source_a_id,
    source_a_value,
    source_b_id,
    source_b_value,
    winning_source,
    resolution_rule,
    now() as logged_at
from conflicts
