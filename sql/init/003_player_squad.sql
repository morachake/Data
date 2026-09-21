CREATE TABLE IF NOT EXISTS staging.player_squad_stints (
    player_name  TEXT NOT NULL,
    wiki_title   TEXT,
    team_id      TEXT NOT NULL,
    club_raw     TEXT,
    season       TEXT NOT NULL DEFAULT 'current',
    position     TEXT,
    shirt_no     TEXT,
    appearances  INT,
    goals        INT,
    source_url   TEXT NOT NULL,
    PRIMARY KEY (player_name, team_id, season)
);
