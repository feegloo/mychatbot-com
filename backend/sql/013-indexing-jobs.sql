-- Migration: Add indexing_jobs job queue
-- Goal: Decouple uploads from indexing so each Cloud Run worker instance
-- processes books independently in parallel, pulling work off a Postgres
-- queue instead of holding a long-running HTTP request open.
--
-- Concurrency model:
--   • Any number of worker instances may compete for jobs.
--   • `SELECT ... FOR UPDATE SKIP LOCKED` guarantees at most one worker
--     claims any given row. This is the canonical Postgres queue pattern
--     used by pg-boss, River, Graphile Worker, etc.
--   • Workers heartbeat on `heartbeat_at`; the reaper in the claim query
--     re-offers jobs whose heartbeat is older than `stale_after`.
--   • `attempts < max_attempts` caps retries so a poison job cannot loop
--     forever.
--
-- Status lifecycle:
--   queued    — waiting for a worker
--   claimed   — a worker reserved it; about to start (brief transitional)
--   running   — worker actively processing; heartbeats update the row
--   done      — indexing finished successfully
--   error     — exhausted retries, terminal
--
-- NOTIFY channel:
--   indexing_jobs_new — fired on INSERT OR on reaper-requeue so idle
--   workers listening on that channel wake up immediately instead of
--   waiting for the 30s poll tick.
BEGIN;

CREATE TABLE IF NOT EXISTS indexing_jobs (
  id                BIGSERIAL PRIMARY KEY,
  conversation_id   TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  collection_name   TEXT NOT NULL,
  -- Local absolute paths inside the worker container. When running on
  -- Cloud Run the worker re-downloads these from GCS on claim if missing.
  file_paths        JSONB NOT NULL,
  storage_namespace TEXT,
  -- Lifecycle.
  status            TEXT NOT NULL DEFAULT 'queued'
    CHECK (status IN ('queued', 'claimed', 'running', 'done', 'error')),
  -- Worker identification: e.g. "chatrag-indexer-00042-abc@instance-xyz".
  -- Kept even after completion for auditability.
  claimed_by        TEXT,
  claimed_at        TIMESTAMPTZ,
  heartbeat_at      TIMESTAMPTZ,
  -- Retry bookkeeping. attempts is incremented atomically inside the claim.
  attempts          INT NOT NULL DEFAULT 0,
  max_attempts      INT NOT NULL DEFAULT 3,
  error_message     TEXT,
  -- Free-form per-job knobs without needing another migration.
  metadata          JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at       TIMESTAMPTZ
);

-- Fast path for the claim query: find the oldest queued/stale-leased row.
-- Partial index keeps it tiny (`done` + `error` rows dominate long-term).
CREATE INDEX IF NOT EXISTS idx_indexing_jobs_pickup
  ON indexing_jobs (created_at)
  WHERE status IN ('queued', 'claimed', 'running');

-- For /conversations/:id status polling and for re-enqueue deduplication.
CREATE INDEX IF NOT EXISTS idx_indexing_jobs_conversation
  ON indexing_jobs (conversation_id, status);

CREATE INDEX IF NOT EXISTS idx_indexing_jobs_heartbeat
  ON indexing_jobs (heartbeat_at)
  WHERE status IN ('claimed', 'running');

-- Auto-maintain updated_at so we don't have to remember in every UPDATE.
CREATE OR REPLACE FUNCTION indexing_jobs_touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at := NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS indexing_jobs_touch_updated_at_trg ON indexing_jobs;
CREATE TRIGGER indexing_jobs_touch_updated_at_trg
  BEFORE UPDATE ON indexing_jobs
  FOR EACH ROW
  EXECUTE FUNCTION indexing_jobs_touch_updated_at();

-- NOTIFY on new queued rows so idle LISTEN'ers wake immediately.
-- Payload is just the job id; listeners re-query the row (saves us from
-- stuffing file_paths into the 8 KB NOTIFY payload and from races where
-- the row is updated between NOTIFY and receipt).
CREATE OR REPLACE FUNCTION indexing_jobs_notify_new()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.status = 'queued' THEN
    PERFORM pg_notify('indexing_jobs_new', NEW.id::text);
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS indexing_jobs_notify_insert_trg ON indexing_jobs;
CREATE TRIGGER indexing_jobs_notify_insert_trg
  AFTER INSERT ON indexing_jobs
  FOR EACH ROW
  EXECUTE FUNCTION indexing_jobs_notify_new();

-- Also fire when the reaper re-queues a stale lease (running → queued).
CREATE OR REPLACE FUNCTION indexing_jobs_notify_requeue()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.status = 'queued' AND OLD.status <> 'queued' THEN
    PERFORM pg_notify('indexing_jobs_new', NEW.id::text);
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS indexing_jobs_notify_requeue_trg ON indexing_jobs;
CREATE TRIGGER indexing_jobs_notify_requeue_trg
  AFTER UPDATE OF status ON indexing_jobs
  FOR EACH ROW
  EXECUTE FUNCTION indexing_jobs_notify_requeue();

COMMIT;
