-- Migration: Add created_at DESC indexes used by the /debug page.
--
-- The debug UI queries every table with `ORDER BY created_at DESC LIMIT 1000`.
-- Without these indexes Postgres does a seq scan + sort, which was the main
-- source of the ~2s lag on /debug page load.
BEGIN;

CREATE INDEX IF NOT EXISTS idx_conversations_created_at
  ON conversations(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_conversation_messages_created_at
  ON conversation_messages(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_suggested_questions_created_at
  ON suggested_questions(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_uploaded_files_created_at
  ON uploaded_files(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_fingerprints_created_at
  ON user_fingerprints(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_conversation_access_tokens_created_at
  ON conversation_access_tokens(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_access_requests_created_at
  ON access_requests(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_processing_jobs_created_at
  ON processing_jobs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_processing_jobs_errors_created_at
  ON processing_jobs_errors(created_at DESC);

COMMIT;
