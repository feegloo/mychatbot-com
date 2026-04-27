-- 016 — Internal messages (Karpathy-style "LLM Wiki" idea file)
--
-- Adds an ``is_internal`` flag to ``conversation_messages`` so the system
-- can persist machine-only artifacts — the per-conversation internal wiki,
-- and any future hidden notes — alongside user-visible chat history without
-- a parallel table.
--
-- Internal messages:
--   - MUST be filtered out of every user-facing API response.
--   - SHOULD be loaded by the answering pipeline and injected into the
--     ANSWER_PROMPT (see python/src/shared/rag.py — Section 3a).
--
-- ``internal_kind`` is a free-form discriminator (e.g., 'wiki') so we can
-- add additional internal artifact types (sleep-consolidation, lint reports,
-- cross-conversation digests) without further migrations.

ALTER TABLE conversation_messages
  ADD COLUMN IF NOT EXISTS is_internal    BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS internal_kind  TEXT;

-- Fast lookup of the most recent internal artifact of a given kind per
-- conversation (RAG injection happens on every /ask call).
CREATE INDEX IF NOT EXISTS conversation_messages_internal_idx
  ON conversation_messages (conversation_id, internal_kind, created_at DESC)
  WHERE is_internal = TRUE;

-- Sanity: an internal_kind only makes sense when is_internal is true.
ALTER TABLE conversation_messages
  DROP CONSTRAINT IF EXISTS conversation_messages_internal_kind_chk;
ALTER TABLE conversation_messages
  ADD CONSTRAINT conversation_messages_internal_kind_chk
  CHECK (internal_kind IS NULL OR is_internal = TRUE);
