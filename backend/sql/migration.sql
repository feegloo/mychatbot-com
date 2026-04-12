BEGIN;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS salt UUID;

UPDATE conversations
SET salt = gen_random_uuid()
WHERE salt IS NULL;

ALTER TABLE conversations
ALTER COLUMN salt SET DEFAULT gen_random_uuid();

ALTER TABLE conversations
ALTER COLUMN salt SET NOT NULL;

COMMIT;

BEGIN;

ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS display_name TEXT;

COMMIT;

-- Migration: Change conversation id from UUID to TEXT (short base62 IDs)
BEGIN;

ALTER TABLE conversation_messages DROP CONSTRAINT IF EXISTS conversation_messages_conversation_id_fkey;
ALTER TABLE access_requests DROP CONSTRAINT IF EXISTS access_requests_conversation_id_fkey;
ALTER TABLE conversation_access_tokens DROP CONSTRAINT IF EXISTS conversation_access_tokens_conversation_id_fkey;
ALTER TABLE suggested_questions DROP CONSTRAINT IF EXISTS suggested_questions_conversation_id_fkey;
ALTER TABLE uploaded_files DROP CONSTRAINT IF EXISTS uploaded_files_conversation_id_fkey;

ALTER TABLE conversations ALTER COLUMN id TYPE TEXT;
ALTER TABLE uploaded_files ALTER COLUMN conversation_id TYPE TEXT;
ALTER TABLE suggested_questions ALTER COLUMN conversation_id TYPE TEXT;
ALTER TABLE conversation_access_tokens ALTER COLUMN conversation_id TYPE TEXT;
ALTER TABLE access_requests ALTER COLUMN conversation_id TYPE TEXT;
ALTER TABLE conversation_messages ALTER COLUMN conversation_id TYPE TEXT;

ALTER TABLE uploaded_files ADD CONSTRAINT uploaded_files_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE;
ALTER TABLE suggested_questions ADD CONSTRAINT suggested_questions_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE;
ALTER TABLE conversation_access_tokens ADD CONSTRAINT conversation_access_tokens_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE;
ALTER TABLE access_requests ADD CONSTRAINT access_requests_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE;
ALTER TABLE conversation_messages ADD CONSTRAINT conversation_messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE;

COMMIT;

-- Migration: Add message_id to suggested_questions (per-message suggested questions)
BEGIN;

ALTER TABLE suggested_questions
ADD COLUMN IF NOT EXISTS message_id UUID REFERENCES conversation_messages(id) ON DELETE CASCADE;

COMMIT;