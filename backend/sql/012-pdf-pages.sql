-- Migration: Add pdf_pages table
-- Goal: Persist per-page OCR/text results during streaming PDF indexing.
--
-- During indexing of large OCR-heavy PDFs (e.g. the 611-page Arabic Mathnawi),
-- each page's extracted text is stored here as soon as it is ready. This lets
-- us:
--   • answer questions against already-parsed pages mid-indexing,
--   • regenerate a fuller welcome message once the full book is parsed,
--   • survive Cloud Run container restarts without re-OCR'ing (cheap DB read
--     instead of re-running OpenAI Vision OCR at ~$0.01/page).
--
-- `source` values:
--   raw    — extracted directly from the PDF text layer
--   ocr    — obtained via OpenAI Vision OCR fallback
--   failed — OCR/extraction errored; row stored with empty text so we can
--            skip it during joining/regen without re-trying every restart
BEGIN;

CREATE TABLE IF NOT EXISTS pdf_pages (
  id               BIGSERIAL PRIMARY KEY,
  conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  file_name        TEXT NOT NULL,
  page_nr          INT  NOT NULL,
  chapter_nr       INT,
  text             TEXT NOT NULL DEFAULT '',
  source           TEXT NOT NULL CHECK (source IN ('raw', 'ocr', 'failed')),
  error_message    TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(conversation_id, file_name, page_nr)
);

CREATE INDEX IF NOT EXISTS idx_pdf_pages_conv_file
  ON pdf_pages(conversation_id, file_name);

CREATE INDEX IF NOT EXISTS idx_pdf_pages_created_at
  ON pdf_pages(created_at DESC);

COMMIT;
