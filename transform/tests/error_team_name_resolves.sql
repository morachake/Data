-- ERROR level test
-- Every raw team name in stg_match for DOMESTIC leagues must resolve to a
-- team_id via team_alias.  Continental competitions (CAF_CL, CAF_CC, etc.)
-- contain clubs from dozens of countries and are excluded — they are validated
-- separately via warn_caf_team_unresolved.sql once seed coverage is complete.
-- Returns unresolved (source_id, league_id, season, team_raw) pairs.

with domestic_leagues as (
    select competition_id
    from {{ ref('competition') }}
    where type = 'league'
),

all_raw_names as (
    select distinct m.source_id, m.league_id, m.season, m.home_team_raw as team_raw
    from {{ ref('stg_match') }} m
    join domestic_leagues d on d.competition_id = m.league_id
    union
    select distinct m.source_id, m.league_id, m.season, m.away_team_raw
    from {{ ref('stg_match') }} m
    join domestic_leagues d on d.competition_id = m.league_id
),

resolved as (
    select distinct alias as team_raw, source_id
    from {{ ref('team_alias') }}
)

select
    a.source_id,
    a.league_id,
    a.season,
    a.team_raw
from all_raw_names a
left join resolved r
    on  r.team_raw   = a.team_raw
    and r.source_id  = a.source_id
where r.team_raw is null
