-- Migration: Add `workers` registry + `jobs` queue for orchestrator-assigned
-- worker pool. Runs alongside the existing `indexing_jobs` queue; both
-- coexist during transition and can be selected per-request via
-- backend `WORKER_MODE` (`inline` | `cloud_run` | `orchestrator`).
--
-- Design rationale:
--   • The backend's main container (orchestrator) picks an idle worker by
--     name from the `workers` table and writes that name into the jobs
--     row. Each worker LISTENs on `jobs_<its-name>` and processes only
--     rows assigned to it — no SKIP LOCKED contention on the hot path.
--   • Hybrid fallback: if the orchestrator can't find an idle worker, it
--     inserts the row with `assigned_worker = NULL` and fires the generic
--     `jobs_unassigned` channel. Any worker that happens to be free can
--     still claim via FOR UPDATE SKIP LOCKED, preserving throughput when
--     the orchestrator loses track (cold-start, DB blip, etc).
--   • Worker liveness is tracked via `last_heartbeat`; the orchestrator
--     skips rows whose heartbeat is older than `stale_after` so crashed
--     containers don't trap work.
--
-- Status lifecycle for `jobs`:
--   waiting    — inserted, no worker assigned (hybrid fallback pool)
--   assigned   — assigned_worker filled, waiting for that worker to claim
--   processing — worker is actively working (heartbeats updating)
--   finished   — terminal success
--   error      — terminal failure (attempts exhausted or non-retriable)
--
-- NOTIFY channels:
--   jobs_<worker_name> — fired when a row is INSERTed with, or UPDATEd to,
--     an assigned_worker. Each worker LISTENs on its own channel only.
--   jobs_unassigned    — fired for rows left assigned_worker IS NULL.
--     Any worker may LISTEN and claim via SKIP LOCKED.

BEGIN;

-- ── workers registry ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS workers (
  -- Stable identifier written by the container on boot. Convention:
  --   orchestrator-<hostname>      for the main backend process
  --   worker-<revision>-<hostname> for pool containers
  name           TEXT PRIMARY KEY,
  -- 'orchestrator' slots can opt out of generic job pickup to keep main
  -- latency predictable when the user is chatting + uploading at once.
  kind           TEXT NOT NULL DEFAULT 'pool'
    CHECK (kind IN ('orchestrator', 'pool')),
  status         TEXT NOT NULL DEFAULT 'starting'
    CHECK (status IN ('starting', 'idle', 'busy', 'offline')),
  -- Job currently being processed (NULL when idle). FK is SET NULL on
  -- job delete so cascading conversation deletes don't trap workers in
  -- a bad state.
  current_job_id BIGINT,
  -- Informational only — rendered in the admin/debug UI for tracing
  -- which deploy rolled out which worker.
  revision       TEXT,
  last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  started_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  metadata       JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Picker query: WHERE status='idle' AND last_heartbeat > NOW()-interval
CREATE INDEX IF NOT EXISTS idx_workers_idle_heartbeat
  ON workers (status, last_heartbeat DESC)
  WHERE status = 'idle';

-- ── jobs queue ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jobs (
  id                BIGSERIAL PRIMARY KEY,
  conversation_id   TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  collection_name   TEXT NOT NULL,
  -- Array of per-file entries. Each entry may be a local absolute path,
  -- a gs:// URI, or pipe-separated candidates (same shape as
  -- indexing_jobs.file_paths for worker code reuse).
  file_paths        JSONB NOT NULL,
  storage_namespace TEXT,
  -- Targeted worker (NULL = up for grabs by any worker via unassigned
  -- channel). FK omitted: the orchestrator may assign to a worker name
  -- that is about to boot, and we don't want a transient FK violation.
  assigned_worker   TEXT,
  status            TEXT NOT NULL DEFAULT 'waiting'
    CHECK (status IN ('waiting', 'assigned', 'processing', 'finished', 'error')),
  -- Human-readable progress line emitted by the worker (e.g. "OCR page
  -- 12/40"). Surfaces in the debug UI and Sentry breadcrumbs.
  worker_message    TEXT,
  attempts          INT NOT NULL DEFAULT 0,
  max_attempts      INT NOT NULL DEFAULT 3,
  error_message     TEXT,
  heartbeat_at      TIMESTAMPTZ,
  metadata          JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  started_at        TIMESTAMPTZ,
  finished_at       TIMESTAMPTZ
);

-- Partial index: keeps the "any open work for this worker" lookup tiny
-- even once finished/error rows dominate the table.
CREATE INDEX IF NOT EXISTS idx_jobs_open_assigned
  ON jobs (assigned_worker, created_at)
  WHERE status IN ('waiting', 'assigned', 'processing');

CREATE INDEX IF NOT EXISTS idx_jobs_open_unassigned
  ON jobs (created_at)
  WHERE status IN ('waiting', 'assigned') AND assigned_worker IS NULL;

CREATE INDEX IF NOT EXISTS idx_jobs_conversation
  ON jobs (conversation_id, status);

CREATE INDEX IF NOT EXISTS idx_jobs_heartbeat
  ON jobs (heartbeat_at)
  WHERE status = 'processing';

-- Add the FK on workers.current_job_id now that jobs exists. Deferred
-- so both CREATE TABLE statements can live in one migration file.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'workers_current_job_id_fkey'
  ) THEN
    ALTER TABLE workers
      ADD CONSTRAINT workers_current_job_id_fkey
      FOREIGN KEY (current_job_id) REFERENCES jobs(id) ON DELETE SET NULL;
  END IF;
END$$;

-- Auto-maintain updated_at.
CREATE OR REPLACE FUNCTION jobs_touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at := NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS jobs_touch_updated_at_trg ON jobs;
CREATE TRIGGER jobs_touch_updated_at_trg
  BEFORE UPDATE ON jobs
  FOR EACH ROW
  EXECUTE FUNCTION jobs_touch_updated_at();

-- NOTIFY routing. Dynamic channel names per worker: `pg_notify` takes
-- TEXT so we can format the channel at runtime. Channel identifiers
-- (used by LISTEN statements on the client side) are safe because
-- worker names are controlled by our container code, not user input.
-- Still, we guard by sanitising to [A-Za-z0-9_-] via replace() in case
-- hostnames contain dots on some platforms.
CREATE OR REPLACE FUNCTION jobs_notify_insert()
RETURNS TRIGGER AS $$
DECLARE
  channel TEXT;
  safe_name TEXT;
BEGIN
  IF NEW.assigned_worker IS NOT NULL THEN
    safe_name := regexp_replace(NEW.assigned_worker, '[^A-Za-z0-9_]', '_', 'g');
    channel := 'jobs_' || safe_name;
  ELSE
    channel := 'jobs_unassigned';
  END IF;
  PERFORM pg_notify(channel, NEW.id::text);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS jobs_notify_insert_trg ON jobs;
CREATE TRIGGER jobs_notify_insert_trg
  AFTER INSERT ON jobs
  FOR EACH ROW
  EXECUTE FUNCTION jobs_notify_insert();

-- Fire again when a previously-unassigned row gets an owner (e.g. an
-- idle worker came online after the job was queued), or when a stale
-- job is reassigned by the reaper.
CREATE OR REPLACE FUNCTION jobs_notify_assign()
RETURNS TRIGGER AS $$
DECLARE
  channel TEXT;
  safe_name TEXT;
BEGIN
  IF NEW.assigned_worker IS NOT NULL
     AND NEW.assigned_worker IS DISTINCT FROM OLD.assigned_worker
  THEN
    safe_name := regexp_replace(NEW.assigned_worker, '[^A-Za-z0-9_]', '_', 'g');
    channel := 'jobs_' || safe_name;
    PERFORM pg_notify(channel, NEW.id::text);
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS jobs_notify_assign_trg ON jobs;
CREATE TRIGGER jobs_notify_assign_trg
  AFTER UPDATE OF assigned_worker ON jobs
  FOR EACH ROW
  EXECUTE FUNCTION jobs_notify_assign();

COMMIT;
