CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY,
  salt UUID NOT NULL,
  display_name TEXT,
  status TEXT NOT NULL DEFAULT 'processing',
  storage_namespace TEXT NOT NULL,
  vector_collection_name TEXT NOT NULL,
  indexing_mode TEXT NOT NULL,
  error_message TEXT,
  parent_message_id TEXT,
  parent_conversation_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS uploaded_files (
  id UUID PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  original_name TEXT NOT NULL,
  stored_name TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  size_bytes BIGINT NOT NULL,
  storage_key TEXT NOT NULL,
  metadata_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversation_messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content TEXT NOT NULL,
  citations_json JSONB,
  user_id INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_fingerprints (
  fingerprint TEXT PRIMARY KEY,
  user_id SERIAL NOT NULL UNIQUE,
  user_agent TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS suggested_questions (
  id UUID PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  message_id TEXT REFERENCES conversation_messages(id) ON DELETE CASCADE,
  question TEXT NOT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversation_access_tokens (
  token TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('owner', 'editor')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS access_requests (
  id UUID PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  display_name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
  editor_token TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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

CREATE INDEX IF NOT EXISTS idx_conversations_parent_conversation_id
  ON conversations(parent_conversation_id);

CREATE INDEX IF NOT EXISTS idx_conversations_parent_message_id
  ON conversations(parent_message_id);

CREATE INDEX IF NOT EXISTS idx_user_fingerprints_fingerprint
  ON user_fingerprints(fingerprint);

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

CREATE TABLE IF NOT EXISTS processing_jobs_errors (
  id              BIGSERIAL PRIMARY KEY,
  uid             UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
  processing_job_id UUID REFERENCES processing_jobs(id) ON DELETE CASCADE,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  file_name       TEXT NOT NULL,
  page_number     INT,
  step            TEXT,
  content_type    TEXT,
  content         TEXT,
  image_path      TEXT,
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
