-- Migration: Cross-conversation generated-image registry.
--
-- Every time DALL-E produces an image for a conversation we also record a
-- row here so *other* conversations can later "borrow" the same image when
-- their creative-writing answers match its description semantically. The
-- semantic match itself is done in a global Chroma collection keyed by
-- `id`; this table is the system of record for serving the asset back
-- (storage_namespace + file_name → /api/storage/<ns>/<file>).
--
-- source_original_names / source_size_bytes capture the uploaded files in
-- the originating conversation at generation time. Re-uploading an
-- identical PDF (same name + size) in a new conversation lets us bias
-- reuse towards images grounded in that same source material.
BEGIN;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS generated_images (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  message_id TEXT REFERENCES conversation_messages(id) ON DELETE SET NULL,
  storage_namespace TEXT NOT NULL,
  file_name TEXT NOT NULL,
  image_title TEXT,
  image_prompt TEXT,
  revised_prompt TEXT,
  user_prompt TEXT,
  description TEXT NOT NULL,
  source_original_names TEXT[] NOT NULL DEFAULT '{}',
  source_size_bytes BIGINT[] NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_generated_images_conversation_id
  ON generated_images(conversation_id);

CREATE INDEX IF NOT EXISTS idx_generated_images_storage_namespace
  ON generated_images(storage_namespace);

-- GIN index so we can quickly find rows whose source files overlap with a
-- set of (original_name) strings from a newly uploaded conversation.
CREATE INDEX IF NOT EXISTS idx_generated_images_source_names
  ON generated_images USING GIN (source_original_names);

COMMIT;
