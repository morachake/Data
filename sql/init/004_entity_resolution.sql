-- ============================================================
-- 004_entity_resolution.sql
--
-- Tables supporting the entity resolution pipeline.
-- Run after 003_core_schema.sql.
-- ============================================================

-- --------------------------------------------------------
-- staging.review_queue
--   Grey-zone player matches awaiting human review.
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS staging.review_queue (
    id          BIGSERIAL PRIMARY KEY,
    name_a      TEXT NOT NULL,
    source_a    TEXT NOT NULL,
    name_b      TEXT NOT NULL,
    source_b    TEXT NOT NULL,
    score       NUMERIC(5,2) NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'rejected', 'skipped')),
    reviewer    TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (name_a, source_a, name_b, source_b)
);

CREATE INDEX IF NOT EXISTS idx_review_queue_status ON staging.review_queue (status);
CREATE INDEX IF NOT EXISTS idx_review_queue_score  ON staging.review_queue (score DESC);

-- --------------------------------------------------------
-- core.player_alias
--   Maps (raw_name, source_id) → canonical player_id.
--   Populated by entity_resolution/player_matcher.py and review_queue.py.
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.player_alias (
    alias           TEXT        NOT NULL,
    source_id       TEXT        NOT NULL,
    player_id       TEXT        NOT NULL REFERENCES core.player(player_id)
                                ON DELETE CASCADE,
    method          TEXT        NOT NULL DEFAULT 'auto_accept'
        CHECK (method IN ('auto_accept', 'manual_review', 'seeded')),
    score           NUMERIC(5,2),
    resolved_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (alias, source_id)
);

CREATE INDEX IF NOT EXISTS idx_player_alias_player ON core.player_alias (player_id);
