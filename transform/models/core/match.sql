{{
  config(
    materialized='table',
    tags=['core', 'partitioned']
  )
}}

/*
  match — reconciled match records.

  Builds on stg_match, resolves raw team names via team_alias, and selects
  the winning row for each fixture using source priority from sources.yml
  (encoded in team_alias source column for now; full reconciliation in Phase 2
  via conflict_log).

  The match_id is deterministic:  md5(season_id || home_team_id || away_team_id)
  so it survives re-runs without creating duplicates.
*/

with raw as (
    -- Normalise en-dash (U+2013) in season labels to plain hyphen so JSONL
    -- files (directory names use ASCII '-') and legacy wiki_results rows
    -- (Wikipedia uses '–') merge cleanly into a single season identifier.
    select
        source_id,
        league_id,
        replace(season, chr(8211), '-') as season,  -- en-dash → hyphen
        home_team_raw,
        away_team_raw,
        home_goals,
        away_goals,
        match_date,
        round,
        status,
        source_url,
        run_id,
        loaded_at
    from {{ ref('stg_match') }}
),

aliases as (
    select
        alias,
        team_id,
        source_id,
        valid_from,
        valid_to
    from {{ ref('team_alias') }}
),

resolved as (
    select
        r.league_id,
        r.season,
        r.league_id || '_' || r.season                    as season_id,
        ha.team_id                                        as home_team_id,
        aa.team_id                                        as away_team_id,
        r.home_team_raw,
        r.away_team_raw,
        r.home_goals,
        r.away_goals,
        r.match_date,
        r.round,
        r.status,
        r.source_id,
        r.source_url,
        r.run_id,
        -- row_number to keep highest-priority source when the same match
        -- appears in multiple sources
        row_number() over (
            partition by r.league_id, r.season, ha.team_id, aa.team_id
            order by
                case r.source_id
                    when 'psl_official'     then 1
                    when 'wikipedia_season' then 2
                    when 'rsssf_tables'     then 3
                    else 99
                end,
                r.loaded_at desc
        ) as rn
    from raw r
    left join aliases ha
           on ha.alias     = r.home_team_raw
          and ha.source_id = r.source_id
    left join aliases aa
           on aa.alias     = r.away_team_raw
          and aa.source_id = r.source_id
    where
        ha.team_id is not null
        and aa.team_id is not null
        and ha.team_id != aa.team_id
)

select
    md5(season_id || home_team_id || away_team_id)  as match_id,
    season_id,
    league_id,
    season,
    match_date,
    home_team_id,
    away_team_id,
    home_goals,
    away_goals,
    case
        when home_goals > away_goals then 'H'
        when home_goals < away_goals then 'A'
        else 'D'
    end                                             as result,
    status,
    round,
    source_id,
    source_url,
    run_id
from resolved
where rn = 1
