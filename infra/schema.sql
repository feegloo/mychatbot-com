-- ChatRAG production-shaped schema.
-- These tables model upload processing, worker ownership locks, ask-message idempotency,
-- and traceable events across Cloud Function, Pub/Sub, Cloud Run server, and worker.

CREATE TABLE IF NOT EXISTS conversations (
    uid TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    file_name TEXT,
    storage_uri TEXT,
    status TEXT NOT NULL DEFAULT 'uploaded',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Synthetic home conversation used before a user uploads a PDF.
INSERT INTO conversations(uid, trace_id, status)
VALUES ('home', 'system-home-trace', 'system')
ON CONFLICT (uid) DO NOTHING;

CREATE TABLE IF NOT EXISTS processing_locks (
    uid TEXT PRIMARY KEY REFERENCES conversations(uid) ON DELETE CASCADE,
    trace_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    file_name TEXT,
    storage_uri TEXT,
    status TEXT NOT NULL DEFAULT 'processing',
    locked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS worker_events (
    id BIGSERIAL PRIMARY KEY,
    uid TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id BIGSERIAL PRIMARY KEY,
    trace_id TEXT NOT NULL UNIQUE,
    uid TEXT NOT NULL REFERENCES conversations(uid) ON DELETE CASCADE DEFAULT 'home',
    fingerprint TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'user',
    value TEXT NOT NULL,
    answer TEXT,
    worker_id TEXT,
    status TEXT NOT NULL DEFAULT 'processing',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Full debug/audit trail for important cross-system events.
-- Every upload, /ask, Pub/Sub publish/receive, lock, worker answer, and SSE event can be stored here.
CREATE TABLE IF NOT EXISTS conversations_metadatas (
    id BIGSERIAL PRIMARY KEY,
    uid TEXT NOT NULL REFERENCES conversations(uid) ON DELETE CASCADE,
    trace_id TEXT NOT NULL,
    fingerprint TEXT,
    source TEXT NOT NULL,
    event_type TEXT NOT NULL,
    topic_name TEXT,
    direction TEXT,
    payload JSONB,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_trace_id ON conversations(trace_id);
CREATE INDEX IF NOT EXISTS idx_processing_locks_worker_id ON processing_locks(worker_id);
CREATE INDEX IF NOT EXISTS idx_worker_events_trace_id ON worker_events(trace_id);
CREATE INDEX IF NOT EXISTS idx_conversation_messages_fingerprint ON conversation_messages(fingerprint);
CREATE INDEX IF NOT EXISTS idx_conversation_messages_uid ON conversation_messages(uid);
CREATE INDEX IF NOT EXISTS idx_conversations_metadatas_uid ON conversations_metadatas(uid);
CREATE INDEX IF NOT EXISTS idx_conversations_metadatas_trace_id ON conversations_metadatas(trace_id);
CREATE INDEX IF NOT EXISTS idx_conversations_metadatas_event_type ON conversations_metadatas(event_type);
