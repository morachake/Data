CREATE TABLE IF NOT EXISTS raw.wiki_player_pages (
    id              BIGSERIAL PRIMARY KEY,
    kind            TEXT        NOT NULL,
    payload         JSONB       NOT NULL,
    source_url      TEXT,
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.players (
    player_id        TEXT PRIMARY KEY,
    wiki_title       TEXT NOT NULL,
    full_name        TEXT,
    date_of_birth    TEXT,
    place_of_birth   TEXT,
    height           TEXT,
    position         TEXT,
    current_club     TEXT,
    nationality      TEXT,
    wikidata_id      TEXT,
    image_url        TEXT,
    bio              TEXT,
    source_url       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS staging.player_career (
    player_id    TEXT NOT NULL,
    years        TEXT NOT NULL,
    club_raw     TEXT NOT NULL,
    appearances  INT,
    goals        INT,
    source_url   TEXT NOT NULL,
    PRIMARY KEY (player_id, years, club_raw)
);

CREATE TABLE IF NOT EXISTS staging.player_injuries (
    player_id   TEXT NOT NULL,
    detail      TEXT NOT NULL,
    source_url  TEXT NOT NULL,
    PRIMARY KEY (player_id, detail)
);

CREATE TABLE IF NOT EXISTS staging.player_season_stats (
    player_name  TEXT NOT NULL,
    season       TEXT NOT NULL,
    club_raw     TEXT,
    stat_type    TEXT NOT NULL,
    stat_value   INT NOT NULL,
    source_url   TEXT NOT NULL,
    PRIMARY KEY (player_name, season, stat_type, club_raw)
);
