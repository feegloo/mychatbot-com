-- Migration: Change conversation_messages.id from UUID to TEXT (short 16-char IDs)
-- Run this on existing databases before deploying.

-- Drop FK constraint on suggested_questions.message_id first
ALTER TABLE suggested_questions
  DROP CONSTRAINT suggested_questions_message_id_fkey;

ALTER TABLE conversation_messages
  ALTER COLUMN id TYPE TEXT;

ALTER TABLE suggested_questions
  ALTER COLUMN message_id TYPE TEXT;

-- Re-add FK constraint
ALTER TABLE suggested_questions
  ADD CONSTRAINT suggested_questions_message_id_fkey
  FOREIGN KEY (message_id) REFERENCES conversation_messages(id) ON DELETE CASCADE;
