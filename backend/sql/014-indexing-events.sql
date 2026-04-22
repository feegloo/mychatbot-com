-- Migration: Add indexing_events table for worker→backend event relay
-- Goal: Since workers run on a separate Cloud Run service from the HTTP
-- backend that serves SSE to the browser, they cannot emit events via the
-- backend's in-process EventEmitter. Instead, workers INSERT event rows
-- here and fire NOTIFY; backend instances LISTEN on 'indexing_events' and
-- relay to subscribed browsers via existing SSE infrastructure.
--
-- Events are also persisted (not just NOTIFY'd) so:
--   • a browser that reconnects mid-indexing can replay missed events
--     (via ``since_id`` query param),
--   • no event is lost if the backend instance handling the SSE stream
--     restarts between the worker emitting and the browser receiving.
--
-- Retention: a Cloud Scheduler / cron task can prune rows older than 24h;
-- nothing in the product depends on long-term retention of these events.
BEGIN;

CREATE TABLE IF NOT EXISTS indexing_events (
  id               BIGSERIAL PRIMARY KEY,
  conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  job_id           BIGINT REFERENCES indexing_jobs(id) ON DELETE CASCADE,
  event_type       TEXT NOT NULL,
  payload          JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  -- Claimed by the backend instance that handled the event's side-effects
  -- (welcome insert, status update, SSE emit). NULL means unclaimed;
  -- handlers atomically flip it to NOW() via UPDATE ... WHERE processed_at
  -- IS NULL to guarantee exactly-once processing across horizontally
  -- scaled backend replicas all LISTEN'ing on 'indexing_events'.
  processed_at     TIMESTAMPTZ
);

-- Browser reconnect replay query: ``WHERE conversation_id = $1 AND id > $2``.
CREATE INDEX IF NOT EXISTS idx_indexing_events_conversation
  ON indexing_events (conversation_id, id);

CREATE INDEX IF NOT EXISTS idx_indexing_events_created_at
  ON indexing_events (created_at);

-- Partial index so the LISTEN handler's claim UPDATE stays fast even
-- after the table grows to millions of processed rows.
CREATE INDEX IF NOT EXISTS idx_indexing_events_unprocessed
  ON indexing_events (id) WHERE processed_at IS NULL;

-- NOTIFY on every event so LISTEN'ing backends get instant delivery.
-- Payload = just the row id; backend SELECTs the full row. Keeps us under
-- the 8 KB NOTIFY payload limit even for large welcome messages.
CREATE OR REPLACE FUNCTION indexing_events_notify_insert()
RETURNS TRIGGER AS $$
BEGIN
  PERFORM pg_notify('indexing_events', NEW.id::text);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS indexing_events_notify_insert_trg ON indexing_events;
CREATE TRIGGER indexing_events_notify_insert_trg
  AFTER INSERT ON indexing_events
  FOR EACH ROW
  EXECUTE FUNCTION indexing_events_notify_insert();

COMMIT;
