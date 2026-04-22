-- Migration: Add processing_jobs_errors table
-- Goal: During processing of a large PDF with hundreds of per-page errors,
--       capture each individual error (with a snapshot of the text/image that
--       caused it) so we can debug root causes from the /debug UI.
--
-- Related: processing_jobs stores one row per (file, step) telemetry event;
--          this table stores fine-grained, per-failure rows linked via FK.
BEGIN;

CREATE TABLE IF NOT EXISTS processing_jobs_errors (
  id              BIGSERIAL PRIMARY KEY,
  uid             UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),

  processing_job_id UUID REFERENCES processing_jobs(id) ON DELETE CASCADE,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,

  file_name       TEXT NOT NULL,
  page_number     INT,
  step            TEXT,

  -- Snapshot of the input that caused the error:
  -- content_type: 'text' | 'ocr' | 'image' | 'chunk' | 'other'
  content_type    TEXT,
  content         TEXT,       -- processed page text / chunk snapshot
  image_path      TEXT,       -- path on disk for image inputs

  -- Full error log (message + timestamp + context from the raising library/API)
  error_type      TEXT,
  error_message   TEXT NOT NULL,
  stack_trace     TEXT,

  worker_id       TEXT,
  retry_count     INT NOT NULL DEFAULT 0,

  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pj_errors_job_id
  ON processing_jobs_errors(processing_job_id);

CREATE INDEX IF NOT EXISTS idx_pj_errors_conversation
  ON processing_jobs_errors(conversation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_pj_errors_file_page
  ON processing_jobs_errors(conversation_id, file_name, page_number);

CREATE INDEX IF NOT EXISTS idx_pj_errors_step
  ON processing_jobs_errors(step, created_at DESC);

COMMIT;
