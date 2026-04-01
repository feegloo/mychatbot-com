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