-- Migration: Drop legacy indexing_jobs queue
--
-- Replaced by the GCP Pub/Sub topic ``chatrag-indexing`` consumed by the
-- ``chatrag-worker`` Cloud Run service. ``indexing_events`` is now the only
-- worker→backend channel; jobs themselves live in Pub/Sub (not Postgres).
--
-- The worker now embeds its UUID job_id and per-job metadata directly in
-- each ``indexing_events.payload`` row, so the FK column ``job_id`` and
-- the entire ``indexing_jobs`` table are no longer needed.

BEGIN;

-- Triggers + functions tied to indexing_jobs.
DROP TRIGGER IF EXISTS indexing_jobs_notify_insert_trg  ON indexing_jobs;
DROP TRIGGER IF EXISTS indexing_jobs_notify_requeue_trg ON indexing_jobs;
DROP TRIGGER IF EXISTS indexing_jobs_touch_updated_at_trg ON indexing_jobs;
DROP FUNCTION IF EXISTS indexing_jobs_notify_new();
DROP FUNCTION IF EXISTS indexing_jobs_notify_requeue();
DROP FUNCTION IF EXISTS indexing_jobs_touch_updated_at();

-- The FK from indexing_events.job_id → indexing_jobs(id) is dropped together
-- with the column. New job_id (UUID, optional) lives in the JSONB payload.
ALTER TABLE IF EXISTS indexing_events DROP COLUMN IF EXISTS job_id;

DROP TABLE IF EXISTS indexing_jobs;

COMMIT;
