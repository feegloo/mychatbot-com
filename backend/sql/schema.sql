-- ChatRAG canonical schema (single source of truth).
--
-- Apply with:
--   docker exec -i chatrag-postgres psql -U chatrag -d chatrag < schema.sql
--
-- For an existing database, also run any migration files numbered above
-- the last one already applied (see backend/sql/0NN-*.sql). For a fresh
-- DB this file alone is sufficient.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- Core conversation model
-- ============================================================================

CREATE TABLE IF NOT EXISTS conversations (
  id                      TEXT PRIMARY KEY,
  salt                    UUID NOT NULL DEFAULT gen_random_uuid(),
  display_name            TEXT,
  status                  TEXT NOT NULL DEFAULT 'processing',
  storage_namespace       TEXT NOT NULL,
  vector_collection_name  TEXT NOT NULL,
  indexing_mode           TEXT NOT NULL,
  error_message           TEXT,
  parent_message_id       TEXT,
  parent_conversation_id  TEXT,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS uploaded_files (
  id               UUID PRIMARY KEY,
  conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  original_name    TEXT NOT NULL,
  stored_name      TEXT NOT NULL,
  mime_type        TEXT NOT NULL,
  size_bytes       BIGINT NOT NULL,
  storage_key      TEXT NOT NULL,
  metadata_json    JSONB,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversation_messages (
  id               TEXT PRIMARY KEY,
  conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role             TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content          TEXT NOT NULL,
  citations_json   JSONB,
  user_id          INT NOT NULL DEFAULT 0,
  is_internal      BOOLEAN NOT NULL DEFAULT FALSE,
  internal_kind    TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT conversation_messages_internal_kind_chk
    CHECK (internal_kind IS NULL OR is_internal = TRUE)
);

CREATE INDEX IF NOT EXISTS conversation_messages_internal_idx
  ON conversation_messages (conversation_id, internal_kind, created_at DESC)
  WHERE is_internal = TRUE;

CREATE TABLE IF NOT EXISTS suggested_questions (
  id               UUID PRIMARY KEY,
  conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  message_id       TEXT REFERENCES conversation_messages(id) ON DELETE CASCADE,
  question         TEXT NOT NULL,
  sort_order       INT NOT NULL DEFAULT 0,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversation_access_tokens (
  token            TEXT PRIMARY KEY,
  conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role             TEXT NOT NULL CHECK (role IN ('owner', 'editor')),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS access_requests (
  id               UUID PRIMARY KEY,
  conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  display_name     TEXT NOT NULL,
  status           TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'approved', 'rejected')),
  editor_token     TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_fingerprints (
  fingerprint  TEXT PRIMARY KEY,
  user_id      SERIAL NOT NULL UNIQUE,
  user_agent   TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- PDF page cache (per-conversation parsed/OCR'd page text)
-- ============================================================================

CREATE TABLE IF NOT EXISTS pdf_pages (
  id               BIGSERIAL PRIMARY KEY,
  conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  file_name        TEXT NOT NULL,
  page_nr          INT NOT NULL,
  chapter_nr       INT,
  text             TEXT NOT NULL DEFAULT '',
  source           TEXT NOT NULL CHECK (source IN ('raw', 'ocr', 'failed')),
  error_message    TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(conversation_id, file_name, page_nr)
);

-- ============================================================================
-- Cross-conversation generated-image registry (DALL-E reuse cache)
-- ============================================================================

CREATE TABLE IF NOT EXISTS generated_images (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id        TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  message_id             TEXT REFERENCES conversation_messages(id) ON DELETE SET NULL,
  storage_namespace      TEXT NOT NULL,
  file_name              TEXT NOT NULL,
  image_title            TEXT,
  image_prompt           TEXT,
  user_prompt            TEXT,
  source_original_names  TEXT[] NOT NULL DEFAULT '{}',
  source_size_bytes      BIGINT[] NOT NULL DEFAULT '{}',
  created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Telemetry: per-step processing jobs + per-error snapshots
-- ============================================================================

CREATE TABLE IF NOT EXISTS processing_jobs (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  file_name        TEXT NOT NULL,
  page_number      INT,
  total_pages      INT,
  status           TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'running', 'completed', 'failed', 'retrying')),
  step             TEXT NOT NULL,
  detail           TEXT,
  error_message    TEXT,
  retry_count      INT NOT NULL DEFAULT 0,
  duration_ms      INT,
  worker_id        TEXT,
  started_at       TIMESTAMPTZ,
  completed_at     TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS processing_jobs_errors (
  id                 BIGSERIAL PRIMARY KEY,
  uid                UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
  processing_job_id  UUID REFERENCES processing_jobs(id) ON DELETE CASCADE,
  conversation_id    TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  file_name          TEXT NOT NULL,
  page_number        INT,
  step               TEXT,
  content_type       TEXT,
  content            TEXT,
  image_path         TEXT,
  error_type         TEXT,
  error_message      TEXT NOT NULL,
  stack_trace        TEXT,
  worker_id          TEXT,
  retry_count        INT NOT NULL DEFAULT 0,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- LLM prompt/response history (debug page)
-- ============================================================================

CREATE TABLE IF NOT EXISTS prompt_history (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id    TEXT REFERENCES conversations(id) ON DELETE CASCADE,
  operation          TEXT NOT NULL,
  model              TEXT NOT NULL,
  prompt_text        TEXT NOT NULL,
  response_text      TEXT,
  prompt_tokens      INT,
  completion_tokens  INT,
  total_tokens       INT,
  cached_tokens      INT DEFAULT 0,
  duration_ms        INT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Worker → backend event relay (chatrag-worker emits, backend SSE replays)
--
-- chatrag-worker (Pub/Sub subscriber) INSERTs progress events here and the
-- AFTER INSERT trigger fires NOTIFY 'indexing_events'. Any backend replica
-- LISTEN'ing relays to subscribed browsers via SSE. ``processed_at`` is
-- claimed atomically to dedupe across horizontally-scaled backends.
--
-- The ``payload`` JSONB carries everything the handler needs, including
-- the worker-side ``job_id`` (Pub/Sub UUID) and per-job metadata
-- (uploadedFileNames, storedToOriginal). There is no FK to a job-queue
-- table because jobs themselves are owned by Pub/Sub.
-- ============================================================================

CREATE TABLE IF NOT EXISTS indexing_events (
  id               BIGSERIAL PRIMARY KEY,
  conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  event_type       TEXT NOT NULL,
  payload          JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at     TIMESTAMPTZ
);

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

-- ============================================================================
-- Indexes
-- ============================================================================

-- Per-conversation lookups
CREATE INDEX IF NOT EXISTS idx_uploaded_files_conversation_id
  ON uploaded_files(conversation_id);
CREATE INDEX IF NOT EXISTS idx_suggested_questions_conversation_id
  ON suggested_questions(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversation_access_tokens_conversation_id
  ON conversation_access_tokens(conversation_id);
CREATE INDEX IF NOT EXISTS idx_access_requests_conversation_id
  ON access_requests(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversation_messages_conversation_id
  ON conversation_messages(conversation_id, created_at);

-- Threading
CREATE INDEX IF NOT EXISTS idx_conversations_parent_conversation_id
  ON conversations(parent_conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversations_parent_message_id
  ON conversations(parent_message_id);

-- Auth
CREATE INDEX IF NOT EXISTS idx_user_fingerprints_fingerprint
  ON user_fingerprints(fingerprint);

-- PDF pages
CREATE INDEX IF NOT EXISTS idx_pdf_pages_conv_file
  ON pdf_pages(conversation_id, file_name);

-- Generated images
CREATE INDEX IF NOT EXISTS idx_generated_images_conversation_id
  ON generated_images(conversation_id);
CREATE INDEX IF NOT EXISTS idx_generated_images_storage_namespace
  ON generated_images(storage_namespace);
CREATE INDEX IF NOT EXISTS idx_generated_images_source_names
  ON generated_images USING GIN (source_original_names);

-- Processing telemetry
CREATE INDEX IF NOT EXISTS idx_processing_jobs_conversation_id
  ON processing_jobs(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_status
  ON processing_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_pj_errors_job_id
  ON processing_jobs_errors(processing_job_id);
CREATE INDEX IF NOT EXISTS idx_pj_errors_conversation
  ON processing_jobs_errors(conversation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pj_errors_file_page
  ON processing_jobs_errors(conversation_id, file_name, page_number);
CREATE INDEX IF NOT EXISTS idx_pj_errors_step
  ON processing_jobs_errors(step, created_at DESC);

-- Prompt history
CREATE INDEX IF NOT EXISTS idx_prompt_history_conversation
  ON prompt_history(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_prompt_history_operation
  ON prompt_history(operation, created_at);

-- Indexing events (browser reconnect replay + unprocessed claim)
CREATE INDEX IF NOT EXISTS idx_indexing_events_conversation
  ON indexing_events(conversation_id, id);
CREATE INDEX IF NOT EXISTS idx_indexing_events_unprocessed
  ON indexing_events(id) WHERE processed_at IS NULL;

-- /debug page recent-N queries
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
CREATE INDEX IF NOT EXISTS idx_pdf_pages_created_at
  ON pdf_pages(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_prompt_history_created
  ON prompt_history(created_at);
CREATE INDEX IF NOT EXISTS idx_indexing_events_created_at
  ON indexing_events(created_at);
