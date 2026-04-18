-- Migration: Add processing_jobs table for file/page processing telemetry
BEGIN;

CREATE TABLE IF NOT EXISTS processing_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  file_name TEXT NOT NULL,
  page_number INT,
  total_pages INT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'running', 'completed', 'failed', 'retrying')),
  step TEXT NOT NULL,
  detail TEXT,
  error_message TEXT,
  retry_count INT NOT NULL DEFAULT 0,
  duration_ms INT,
  worker_id TEXT,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_processing_jobs_conversation_id
  ON processing_jobs(conversation_id, created_at);

CREATE INDEX IF NOT EXISTS idx_processing_jobs_status
  ON processing_jobs(status, created_at);

COMMIT;
