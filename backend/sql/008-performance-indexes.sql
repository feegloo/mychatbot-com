-- Migration: Add indexes for thread query performance
BEGIN;

-- Used by getConversation() when looking up the branched-from parent message
CREATE INDEX IF NOT EXISTS idx_conversation_messages_id
  ON conversation_messages(id);

-- Used by getConversation() for thread lookups by parent_conversation_id
CREATE INDEX IF NOT EXISTS idx_conversations_parent_conversation_id
  ON conversations(parent_conversation_id);

-- Used by getConversation() for message-level thread lookups
CREATE INDEX IF NOT EXISTS idx_conversations_parent_message_id
  ON conversations(parent_message_id);

COMMIT;
