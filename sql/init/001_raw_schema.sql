CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;

-- Every table scraped from a Wikipedia season page, stored as-is
CREATE TABLE IF NOT EXISTS raw.wiki_tables (
    id           BIGSERIAL PRIMARY KEY,
    source       TEXT        NOT NULL,
    source_url   TEXT        NOT NULL,
    season       TEXT        NOT NULL,
    table_index  INT         NOT NULL,
    section      TEXT,
    rows         JSONB       NOT NULL,
    scraped_at   TIMESTAMPTZ NOT NULL,
    loaded_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Match results parsed out of the season results matrix
CREATE TABLE IF NOT EXISTS staging.wiki_results (
    season        TEXT NOT NULL,
    home_team_raw TEXT NOT NULL,
    away_team_raw TEXT NOT NULL,
    home_goals    INT  NOT NULL,
    away_goals    INT  NOT NULL,
    source_url    TEXT NOT NULL,
    PRIMARY KEY (season, home_team_raw, away_team_raw)
);
