{{
  config(
    materialized='table',
    tags=['core']
  )
}}

/*
  competition — one row per league / cup defined in config/leagues.yml.

  Populated from the team seed's competition_id values plus hard-coded
  metadata.  In a later phase this can be sourced from a competitions seed.
*/

with seed as (
    select distinct
        competition_id,
        country
    from {{ ref('team') }}
    where competition_id is not null
),

manual as (
    -- Competitions without a team seed entry yet (continental, wave 2+).
    -- Extend this as leagues are added.
    select
        competition_id,
        name,
        country,
        type,
        wave,
        language,
        season_format
    from (values
        ('RSA_PREM',    'South African Premiership',  'South Africa', 'league',      1, 'en', 'aug_may'),
        ('EGY_PL',      'Egyptian Premier League',    'Egypt',        'league',      1, 'ar', 'tbd'),
        ('MAR_BOTOLA',  'Botola Pro',                 'Morocco',      'league',      1, 'fr', 'tbd'),
        ('TZA_PL',      'Tanzania Premier League',    'Tanzania',     'league',      1, 'en', 'tbd'),
        ('KEN_PL',      'FKF Premier League',         'Kenya',        'league',      1, 'en', 'tbd'),
        ('CAF_CL',      'CAF Champions League',       'Africa',       'continental', 1, 'en', 'irregular'),
        ('CAF_CC',      'CAF Confederation Cup',      'Africa',       'continental', 1, 'en', 'irregular'),
        ('ALG_L1',      'Ligue Professionnelle 1',    'Algeria',      'league',      2, 'fr', 'tbd'),
        ('TUN_L1',      'Ligue 1 (Tunisia)',          'Tunisia',      'league',      2, 'fr', 'tbd'),
        ('NGA_NPFL',    'Nigeria Premier Football League','Nigeria',   'league',      2, 'en', 'tbd'),
        ('CIV_L1',      'Ligue 1 (Ivory Coast)',      'Ivory Coast',  'league',      2, 'fr', 'tbd'),
        ('GHA_GPL',     'Ghana Premier League',       'Ghana',        'league',      2, 'en', 'tbd')
    ) as t(competition_id, name, country, type, wave, language, season_format)
)

select
    m.competition_id,
    m.name,
    m.country,
    m.type,
    m.wave,
    m.language,
    m.season_format
from manual m
