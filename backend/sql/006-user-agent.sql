-- Migration: Add user_agent column to user_fingerprints
BEGIN;

ALTER TABLE user_fingerprints
ADD COLUMN IF NOT EXISTS user_agent TEXT;

COMMIT;
