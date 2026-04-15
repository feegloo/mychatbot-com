-- Migration: Add user fingerprints, user_id on messages, and thread support
BEGIN;

-- User fingerprint → sequential userId mapping
CREATE TABLE IF NOT EXISTS user_fingerprints (
  fingerprint TEXT PRIMARY KEY,
  user_id SERIAL NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_fingerprints_fingerprint
  ON user_fingerprints(fingerprint);

-- Add user_id to conversation messages (0 = assistant, 1+ = real users)
ALTER TABLE conversation_messages
ADD COLUMN IF NOT EXISTS user_id INT NOT NULL DEFAULT 0;

-- Add parent_message_id to conversations for thread support
-- When a user replies to a shared message, a new "thread" conversation is created
-- with parent_message_id pointing to the original shared message
ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS parent_message_id TEXT REFERENCES conversation_messages(id) ON DELETE SET NULL;

COMMIT;
