import { Pool, QueryResultRow } from 'pg'
import { config } from './config.js'

export const pool = new Pool({
  connectionString: config.databaseUrl,
  max: config.dbPoolMax,
  idleTimeoutMillis: config.dbIdleTimeoutMs,
  connectionTimeoutMillis: config.dbConnectionTimeoutMs,
})

// Surface pool-level connection errors instead of crashing the process.
pool.on('error', (err) => {
  console.error('[db] idle client error', err)
})

export async function query<T extends QueryResultRow = any>(sql: string, params: any[] = []) {
  return pool.query<T>(sql, params)
}

// Indexes used by the /debug page. Kept idempotent so it's safe to run on
// every startup; Postgres skips any that already exist.
const DEBUG_INDEX_STATEMENTS = [
  'CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at DESC)',
  'CREATE INDEX IF NOT EXISTS idx_conversation_messages_created_at ON conversation_messages(created_at DESC)',
  'CREATE INDEX IF NOT EXISTS idx_suggested_questions_created_at ON suggested_questions(created_at DESC)',
  'CREATE INDEX IF NOT EXISTS idx_uploaded_files_created_at ON uploaded_files(created_at DESC)',
  'CREATE INDEX IF NOT EXISTS idx_user_fingerprints_created_at ON user_fingerprints(created_at DESC)',
  'CREATE INDEX IF NOT EXISTS idx_conversation_access_tokens_created_at ON conversation_access_tokens(created_at DESC)',
  'CREATE INDEX IF NOT EXISTS idx_access_requests_created_at ON access_requests(created_at DESC)',
  'CREATE INDEX IF NOT EXISTS idx_processing_jobs_created_at ON processing_jobs(created_at DESC)',
  'CREATE INDEX IF NOT EXISTS idx_processing_jobs_errors_created_at ON processing_jobs_errors(created_at DESC)',
]

// Idempotent bootstrap for the cross-conversation generated-images table.
// Applied on every startup so fresh deploys don't require running the
// 011-generated-images.sql migration out-of-band.
const GENERATED_IMAGES_STATEMENTS = [
  `CREATE TABLE IF NOT EXISTS generated_images (
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
   )`,
  // Backfill for older deployments that created the table without user_prompt.
  `ALTER TABLE generated_images ADD COLUMN IF NOT EXISTS user_prompt TEXT`,
  'CREATE INDEX IF NOT EXISTS idx_generated_images_conversation_id ON generated_images(conversation_id)',
  'CREATE INDEX IF NOT EXISTS idx_generated_images_storage_namespace ON generated_images(storage_namespace)',
  'CREATE INDEX IF NOT EXISTS idx_generated_images_source_names ON generated_images USING GIN (source_original_names)',
]

// Idempotent bootstrap for the pdf_pages table. Applied on every startup so
// fresh deploys don't require running the 012-pdf-pages.sql migration
// out-of-band. See that file for the rationale.
const PDF_PAGES_STATEMENTS = [
  `CREATE TABLE IF NOT EXISTS pdf_pages (
     id BIGSERIAL PRIMARY KEY,
     conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
     file_name TEXT NOT NULL,
     page_nr INT NOT NULL,
     chapter_nr INT,
     text TEXT NOT NULL DEFAULT '',
     source TEXT NOT NULL CHECK (source IN ('raw', 'ocr', 'failed')),
     error_message TEXT,
     created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
     UNIQUE(conversation_id, file_name, page_nr)
   )`,
  'CREATE INDEX IF NOT EXISTS idx_pdf_pages_conv_file ON pdf_pages(conversation_id, file_name)',
  'CREATE INDEX IF NOT EXISTS idx_pdf_pages_created_at ON pdf_pages(created_at DESC)',
]

// Idempotent bootstrap for indexing_events relay table. See schema.sql for
// the design rationale (worker→backend decoupling via Pub/Sub job delivery
// and DB-persisted progress events for browser reconnect replay).
//
// job_id (Pub/Sub UUID) and per-job metadata are embedded in the JSONB
// payload by the worker — there is no longer a foreign-key relation to a
// jobs table. Migration 015-drop-indexing-jobs.sql removes the legacy FK.
const INDEXING_EVENTS_STATEMENTS = [
  `CREATE TABLE IF NOT EXISTS indexing_events (
     id BIGSERIAL PRIMARY KEY,
     conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
     event_type TEXT NOT NULL,
     payload JSONB NOT NULL DEFAULT '{}'::jsonb,
     created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
     processed_at TIMESTAMPTZ
   )`,
  // Drop the legacy FK column on existing DBs that pre-date the Pub/Sub cutover.
  'ALTER TABLE indexing_events DROP COLUMN IF EXISTS job_id',
  'CREATE INDEX IF NOT EXISTS idx_indexing_events_conversation ON indexing_events (conversation_id, id)',
  'CREATE INDEX IF NOT EXISTS idx_indexing_events_created_at ON indexing_events (created_at)',
  'CREATE INDEX IF NOT EXISTS idx_indexing_events_unprocessed ON indexing_events (id) WHERE processed_at IS NULL',
  `CREATE OR REPLACE FUNCTION indexing_events_notify_insert()
   RETURNS TRIGGER AS $$
   BEGIN
     PERFORM pg_notify('indexing_events', NEW.id::text);
     RETURN NEW;
   END;
   $$ LANGUAGE plpgsql`,
  'DROP TRIGGER IF EXISTS indexing_events_notify_insert_trg ON indexing_events',
  `CREATE TRIGGER indexing_events_notify_insert_trg
     AFTER INSERT ON indexing_events
     FOR EACH ROW
     EXECUTE FUNCTION indexing_events_notify_insert()`,
]

export async function ensureDebugIndexes(): Promise<void> {
  for (const stmt of DEBUG_INDEX_STATEMENTS) {
    try {
      await pool.query(stmt)
    } catch (err) {
      // Don't block server startup on a missing table (e.g. fresh DB where
      // schema.sql hasn't been applied yet); log and continue.
      console.warn('[db] ensureDebugIndexes failed:', (err as Error).message)
    }
  }
  for (const stmt of GENERATED_IMAGES_STATEMENTS) {
    try {
      await pool.query(stmt)
    } catch (err) {
      console.warn('[db] ensureGeneratedImagesSchema failed:', (err as Error).message)
    }
  }
  for (const stmt of PDF_PAGES_STATEMENTS) {
    try {
      await pool.query(stmt)
    } catch (err) {
      console.warn('[db] ensurePdfPagesSchema failed:', (err as Error).message)
    }
  }
  for (const stmt of INDEXING_EVENTS_STATEMENTS) {
    try {
      await pool.query(stmt)
    } catch (err) {
      console.warn('[db] ensureIndexingEventsSchema failed:', (err as Error).message)
    }
  }
}
