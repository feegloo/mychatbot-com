-- Migration: Add parent_conversation_id for conversations branched from shared conversations
-- When a viewer opens a shared conversation and replies, a new thread is created
-- with parent_conversation_id pointing to the shared conversation (no specific message).
-- This differs from message-level threads which use parent_message_id.
BEGIN;

ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS parent_conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_conversations_parent_conversation_id
  ON conversations(parent_conversation_id);

COMMIT;
