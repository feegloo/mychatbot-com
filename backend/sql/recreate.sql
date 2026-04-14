-- WARNING: This drops ALL data and recreates the database from scratch.
-- Usage: docker exec -i chatrag-postgres psql -U chatrag -d postgres -f /dev/stdin < backend/sql/recreate.sql

DROP DATABASE IF EXISTS chatrag;
CREATE DATABASE chatrag OWNER chatrag;

\connect chatrag

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE conversations (
  id TEXT PRIMARY KEY,
  salt UUID NOT NULL,
  display_name TEXT,
  status TEXT NOT NULL DEFAULT 'processing',
  storage_namespace TEXT NOT NULL,
  vector_collection_name TEXT NOT NULL,
  indexing_mode TEXT NOT NULL,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE uploaded_files (
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

CREATE TABLE conversation_messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content TEXT NOT NULL,
  citations_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE suggested_questions (
  id UUID PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  message_id TEXT REFERENCES conversation_messages(id) ON DELETE CASCADE,
  question TEXT NOT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE conversation_access_tokens (
  token TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('owner', 'editor')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE access_requests (
  id UUID PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  display_name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
  editor_token TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_uploaded_files_conversation_id ON uploaded_files(conversation_id);
CREATE INDEX idx_suggested_questions_conversation_id ON suggested_questions(conversation_id);
CREATE INDEX idx_conversation_access_tokens_conversation_id ON conversation_access_tokens(conversation_id);
CREATE INDEX idx_access_requests_conversation_id ON access_requests(conversation_id);
CREATE INDEX idx_conversation_messages_conversation_id ON conversation_messages(conversation_id, created_at);
