-- ============================================================
-- 003_core_schema.sql
--
-- Core business entity schema and Phase 1 staging additions.
-- Run once after 001_raw_schema.sql and 002_players.sql.
-- Idempotent: all statements use CREATE TABLE IF NOT EXISTS
-- and CREATE INDEX IF NOT EXISTS.
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- CORE schema
-- ────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS core;

-- --------------------------------------------------------
-- competition  (league / cup)
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.competition (
    competition_id   TEXT PRIMARY KEY,          -- e.g. RSA_PREM, CAF_CL
    name             TEXT NOT NULL,
    country          TEXT,
    type             TEXT DEFAULT 'league',     -- league | cup | continental
    wave             INT,
    language         TEXT DEFAULT 'en',
    season_format    TEXT,                      -- aug_may | jan_dec | irregular
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- --------------------------------------------------------
-- season  (one per competition per year)
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.season (
    season_id        TEXT PRIMARY KEY,          -- RSA_PREM_2024-25
    competition_id   TEXT NOT NULL REFERENCES core.competition(competition_id),
    season_label     TEXT NOT NULL,             -- "2024-25"
    start_date       DATE,
    end_date         DATE,
    expected_teams   INT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_season_comp_label
    ON core.season (competition_id, season_label);

-- --------------------------------------------------------
-- team
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.team (
    team_id          TEXT PRIMARY KEY,          -- e.g. RSA_ORLANDO_PIRATES
    name             TEXT NOT NULL,
    country          TEXT,
    city             TEXT,
    founded_year     INT,
    wikipedia_title  TEXT,
    wikidata_id      TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- --------------------------------------------------------
-- player
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.player (
    player_id        TEXT PRIMARY KEY,          -- UUID assigned during entity resolution
    full_name        TEXT NOT NULL,
    known_as         TEXT,                      -- common short name
    nationality      TEXT,
    date_of_birth    DATE,
    dob_confidence   TEXT DEFAULT 'unknown'     -- high | medium | low | unknown
        CHECK (dob_confidence IN ('high', 'medium', 'low', 'unknown')),
    place_of_birth   TEXT,
    position         TEXT,                      -- GK | CB | LB | RB | CDM | CM | CAM | LW | RW | CF | ST
    height_cm        INT,
    wikidata_id      TEXT,
    image_url        TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_player_dob ON core.player (date_of_birth);
CREATE INDEX IF NOT EXISTS idx_player_position ON core.player (position);

-- --------------------------------------------------------
-- match
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.match (
    match_id         TEXT PRIMARY KEY,          -- deterministic: season_id|date|home|away
    season_id        TEXT NOT NULL REFERENCES core.season(season_id),
    match_date       DATE,
    home_team_id     TEXT REFERENCES core.team(team_id),
    away_team_id     TEXT REFERENCES core.team(team_id),
    home_goals       INT,
    away_goals       INT,
    status           TEXT NOT NULL DEFAULT 'played'
        CHECK (status IN ('played', 'postponed', 'abandoned', 'awarded', 'unknown')),
    round            TEXT,
    source_id        TEXT NOT NULL,             -- winning source after reconciliation
    source_url       TEXT,
    run_id           TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_match_season   ON core.match (season_id);
CREATE INDEX IF NOT EXISTS idx_match_date     ON core.match (match_date);
CREATE INDEX IF NOT EXISTS idx_match_home     ON core.match (home_team_id);
CREATE INDEX IF NOT EXISTS idx_match_away     ON core.match (away_team_id);

-- --------------------------------------------------------
-- goal
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.goal (
    goal_id          BIGSERIAL PRIMARY KEY,
    match_id         TEXT NOT NULL REFERENCES core.match(match_id),
    player_id        TEXT REFERENCES core.player(player_id),
    team_id          TEXT REFERENCES core.team(team_id),
    minute           INT CHECK (minute BETWEEN 0 AND 120),
    is_own_goal      BOOLEAN NOT NULL DEFAULT false,
    is_penalty       BOOLEAN NOT NULL DEFAULT false,
    source_id        TEXT NOT NULL,
    source_url       TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_goal_match    ON core.goal (match_id);
CREATE INDEX IF NOT EXISTS idx_goal_player   ON core.goal (player_id);

-- --------------------------------------------------------
-- appearance (one row per player per match)
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.appearance (
    appearance_id    BIGSERIAL PRIMARY KEY,
    match_id         TEXT NOT NULL REFERENCES core.match(match_id),
    player_id        TEXT NOT NULL REFERENCES core.player(player_id),
    team_id          TEXT NOT NULL REFERENCES core.team(team_id),
    started          BOOLEAN NOT NULL DEFAULT false,
    minutes_played   INT CHECK (minutes_played BETWEEN 0 AND 120),
    shirt_number     INT,
    position_played  TEXT,
    source_id        TEXT NOT NULL,
    source_url       TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (match_id, player_id, team_id)
);

CREATE INDEX IF NOT EXISTS idx_appearance_match  ON core.appearance (match_id);
CREATE INDEX IF NOT EXISTS idx_appearance_player ON core.appearance (player_id);

-- --------------------------------------------------------
-- player_club_spell (continuous stint at one club)
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.player_club_spell (
    spell_id         BIGSERIAL PRIMARY KEY,
    player_id        TEXT NOT NULL REFERENCES core.player(player_id),
    team_id          TEXT NOT NULL REFERENCES core.team(team_id),
    competition_id   TEXT REFERENCES core.competition(competition_id),
    start_season     TEXT,                      -- first season of the spell
    end_season       TEXT,                      -- last season (null = current)
    loan             BOOLEAN NOT NULL DEFAULT false,
    source_id        TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_spell_player ON core.player_club_spell (player_id);
CREATE INDEX IF NOT EXISTS idx_spell_team   ON core.player_club_spell (team_id);

-- --------------------------------------------------------
-- league_season_coverage  (populated by dbt; read-only for app)
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.league_season_coverage (
    season_id             TEXT PRIMARY KEY REFERENCES core.season(season_id),
    pct_matches_with_result   NUMERIC(5,2),
    pct_goals_with_scorer     NUMERIC(5,2),
    pct_matches_with_lineups  NUMERIC(5,2),
    pct_players_with_dob      NUMERIC(5,2),
    tier                      TEXT
        CHECK (tier IN ('A', 'B', 'C', NULL)),
    computed_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- --------------------------------------------------------
-- conflict_log  (records multi-source disagreements)
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.conflict_log (
    conflict_id       BIGSERIAL PRIMARY KEY,
    entity_type       TEXT NOT NULL,            -- match | goal | player
    entity_id         TEXT NOT NULL,
    field             TEXT NOT NULL,
    source_a_id       TEXT NOT NULL,
    source_a_value    TEXT,
    source_b_id       TEXT NOT NULL,
    source_b_value    TEXT,
    winning_source    TEXT NOT NULL,
    resolution_rule   TEXT,
    logged_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conflict_entity ON core.conflict_log (entity_type, entity_id);


-- ────────────────────────────────────────────────────────────
-- STAGING additions (Phase 1)
-- ────────────────────────────────────────────────────────────

-- Normalised match rows (from any source, before reconciliation)
CREATE TABLE IF NOT EXISTS staging.stg_match (
    id               BIGSERIAL PRIMARY KEY,
    league_id        TEXT NOT NULL,
    season           TEXT NOT NULL,
    home_team_raw    TEXT NOT NULL,
    away_team_raw    TEXT NOT NULL,
    home_goals       INT,
    away_goals       INT,
    match_date       DATE,
    round            TEXT,
    status           TEXT NOT NULL DEFAULT 'played',
    source_id        TEXT NOT NULL,
    source_url       TEXT,
    run_id           TEXT,
    loaded_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_stg_match_league_season
    ON staging.stg_match (league_id, season);

-- Goal events (from match-report sources — Phase 2+)
CREATE TABLE IF NOT EXISTS staging.stg_goal (
    id               BIGSERIAL PRIMARY KEY,
    league_id        TEXT NOT NULL,
    season           TEXT NOT NULL,
    match_date       DATE,
    home_team_raw    TEXT,
    away_team_raw    TEXT,
    scorer_raw       TEXT,
    team_raw         TEXT,
    minute           INT,
    is_own_goal      BOOLEAN DEFAULT false,
    is_penalty       BOOLEAN DEFAULT false,
    source_id        TEXT NOT NULL,
    source_url       TEXT,
    run_id           TEXT,
    loaded_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Appearance records (from lineups — Phase 2+)
CREATE TABLE IF NOT EXISTS staging.stg_appearance (
    id               BIGSERIAL PRIMARY KEY,
    league_id        TEXT NOT NULL,
    season           TEXT NOT NULL,
    match_date       DATE,
    home_team_raw    TEXT,
    away_team_raw    TEXT,
    player_raw       TEXT NOT NULL,
    team_raw         TEXT NOT NULL,
    started          BOOLEAN DEFAULT false,
    minutes_played   INT,
    shirt_number     INT,
    position_raw     TEXT,
    source_id        TEXT NOT NULL,
    source_url       TEXT,
    run_id           TEXT,
    loaded_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Squads (from Wikipedia squad tables)
CREATE TABLE IF NOT EXISTS staging.stg_squad (
    id               BIGSERIAL PRIMARY KEY,
    league_id        TEXT NOT NULL,
    season           TEXT NOT NULL,
    team_raw         TEXT,
    player_raw       TEXT,
    nationality_raw  TEXT,
    position_raw     TEXT,
    shirt_number     INT,
    source_id        TEXT NOT NULL,
    source_url       TEXT,
    loaded_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Standings rows (one per team per season per source)
CREATE TABLE IF NOT EXISTS staging.stg_standing (
    id               BIGSERIAL PRIMARY KEY,
    league_id        TEXT NOT NULL,
    season           TEXT NOT NULL,
    team_raw         TEXT NOT NULL,
    position         INT,
    played           INT,
    won              INT,
    drawn            INT,
    lost             INT,
    goals_for        INT,
    goals_against    INT,
    goal_diff        INT,
    points           INT,
    source_id        TEXT NOT NULL,
    source_url       TEXT,
    run_id           TEXT,
    loaded_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_stg_standing_league_season
    ON staging.stg_standing (league_id, season);

-- Player profile rows (Wikipedia infobox data)
CREATE TABLE IF NOT EXISTS staging.stg_player_profile (
    id               BIGSERIAL PRIMARY KEY,
    player_raw       TEXT NOT NULL,
    nationality_raw  TEXT,
    dob_raw          TEXT,
    height_raw       TEXT,
    position_raw     TEXT,
    wikidata_id      TEXT,
    image_url        TEXT,
    source_url       TEXT,
    run_id           TEXT,
    loaded_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Parse failures — kept separate so failures don't pollute good rows
CREATE TABLE IF NOT EXISTS staging.parse_failures (
    id               BIGSERIAL PRIMARY KEY,
    source_id        TEXT NOT NULL,
    league_id        TEXT,
    season           TEXT,
    source_url       TEXT,
    run_id           TEXT,
    block_type       TEXT,
    block_index      INT,
    error_type       TEXT,
    error_detail     TEXT,
    raw_payload      JSONB,
    failed_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
