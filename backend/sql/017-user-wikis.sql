-- Migration 017: per-user master knowledge wiki
--
-- Stores one synthesised cross-conversation wiki per user, keyed by
-- user_id (from user_fingerprints).  Built lazily whenever a user asks
-- a question and has ≥ 1 conversation wiki ready; refreshed with a
-- 30-minute cooldown to avoid redundant LLM calls.
--
-- Apply with:
--   docker exec -i chatrag-postgres psql -U chatrag -d chatrag < 017-user-wikis.sql

CREATE TABLE IF NOT EXISTS user_wikis (
  user_id       INT     PRIMARY KEY,
  content       TEXT    NOT NULL,
  source_count  INT     NOT NULL DEFAULT 0,
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
