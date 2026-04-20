-- Migration: Add prompt_history table for full LLM prompt/response logging
BEGIN;

CREATE TABLE IF NOT EXISTS prompt_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
  operation TEXT NOT NULL,
  model TEXT NOT NULL,
  prompt_text TEXT NOT NULL,
  response_text TEXT,
  prompt_tokens INT,
  completion_tokens INT,
  total_tokens INT,
  cached_tokens INT DEFAULT 0,
  duration_ms INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prompt_history_conversation
  ON prompt_history(conversation_id, created_at);

CREATE INDEX IF NOT EXISTS idx_prompt_history_operation
  ON prompt_history(operation, created_at);

CREATE INDEX IF NOT EXISTS idx_prompt_history_created
  ON prompt_history(created_at);

-- Auto-cleanup: keep last 30 days of prompt history
-- Run periodically: DELETE FROM prompt_history WHERE created_at < NOW() - INTERVAL '30 days';

COMMIT;
