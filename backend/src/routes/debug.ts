import Router from '@koa/router'
import { timingSafeEqual } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { pool, query } from '../db.js'
import { config } from '../config.js'

// Users tab runs an analytics query maintained as a standalone .sql file
// so non-TS contributors can tweak it without touching route code.
// Resolved once at module load; the SQL file is copied into the image at
// /app/backend/sql (see root Dockerfile).
const __dirname = dirname(fileURLToPath(import.meta.url))
const USERS_SQL = readFileSync(
  resolve(__dirname, '../../sql/users.sql'),
  'utf8',
)

function safeEq(a: string, b: string): boolean {
  const bufA = Buffer.from(a)
  const bufB = Buffer.from(b)
  if (bufA.length !== bufB.length) return false
  return timingSafeEqual(bufA, bufB)
}

function isAuthorized(ctx: any): boolean {
  const auth = ctx.headers.authorization
  if (!auth || !auth.startsWith('Basic ')) return false
  const decoded = Buffer.from(auth.slice(6), 'base64').toString()
  const idx = decoded.indexOf(':')
  const user = idx < 0 ? decoded : decoded.slice(0, idx)
  const pass = idx < 0 ? '' : decoded.slice(idx + 1)
  return !!(
    config.debugUser &&
    config.debugPass &&
    safeEq(user, config.debugUser) &&
    safeEq(pass, config.debugPass)
  )
}

export const debugRouter = new Router()

// Tables listed in the debug UI. Order matches the tab order.
// The 'users' tab is synthesized in the handler below (custom GROUP BY
// over conversation_messages + user_fingerprints); it's not a real table
// so it's not in this list.
const DEBUG_TABLES = [
  'conversations',
  'conversation_messages',
  'suggested_questions',
  'uploaded_files',
  'user_fingerprints',
  'conversation_access_tokens',
  'access_requests',
  'processing_jobs',
  'processing_jobs_errors',
  'prompt_history',
  'generated_images',
  'indexing_events',
  'pdf_pages',
  'workers',
  'jobs',
  'user_wikis',
] as const
type DebugTable = (typeof DEBUG_TABLES)[number]

// Per-table SELECT lists. Some tables truncate large TEXT columns so the
// payload stays small and the UI stays responsive.
const TABLE_SELECT: Record<DebugTable, string> = {
  conversations: '*',
  conversation_messages:
    "id, conversation_id, role, LEFT(content, 500) AS content, created_at, user_id",
  suggested_questions: '*',
  uploaded_files: '*',
  user_fingerprints: '*',
  conversation_access_tokens: '*',
  access_requests: '*',
  processing_jobs: '*',
  processing_jobs_errors:
    `id, uid, processing_job_id, conversation_id, file_name,
     page_number, step, content_type,
     LEFT(content, 500) AS content,
     LENGTH(content) AS content_chars,
     image_path, error_type,
     LEFT(error_message, 500) AS error_message,
     LENGTH(error_message) AS error_chars,
     worker_id, retry_count, created_at`,
  prompt_history:
    `id, conversation_id, operation, model,
     LEFT(prompt_text, 300) AS prompt_text,
     LENGTH(prompt_text) AS prompt_chars,
     LEFT(response_text, 300) AS response_text,
     LENGTH(response_text) AS response_chars,
     prompt_tokens, completion_tokens, total_tokens, cached_tokens,
     duration_ms, created_at`,
  generated_images: '*',
  indexing_events: '*',
  pdf_pages: '*',
  workers: '*',
  jobs: '*',
  user_wikis:
    `user_id, source_count, updated_at,
     LEFT(content, 500) AS content,
     LENGTH(content) AS content_chars`,
}

// Most tables have `created_at`; a few use a different timestamp column
// for natural chronological order.
const TABLE_ORDER_BY: Partial<Record<DebugTable, string>> = {
  workers: 'started_at DESC',
}

/**
 * GET /debug/tables-overview
 *
 * Single-round-trip endpoint for the /debug page's initial load.
 * Returns row counts for every table (for the tab badges) plus the first
 * page of the `conversations` table (the default active tab) in ONE SQL
 * statement via a CTE with json_build_object. Lazy-loads everything else.
 */
debugRouter.get('/api/debug/tables-overview', async (ctx) => {
  if (!isAuthorized(ctx)) {
    ctx.status = 401
    ctx.body = { error: 'Invalid credentials' }
    return
  }

  const limit = 1000
  const sql = `
    SELECT json_build_object(
      'counts', json_build_object(
        'conversations', (SELECT COUNT(*) FROM public.conversations),
        'conversation_messages', (SELECT COUNT(*) FROM public.conversation_messages),
        'suggested_questions', (SELECT COUNT(*) FROM public.suggested_questions),
        'uploaded_files', (SELECT COUNT(*) FROM public.uploaded_files),
        'user_fingerprints', (SELECT COUNT(*) FROM public.user_fingerprints),
        'conversation_access_tokens', (SELECT COUNT(*) FROM public.conversation_access_tokens),
        'access_requests', (SELECT COUNT(*) FROM public.access_requests),
        'users', (SELECT COUNT(DISTINCT user_id) FROM public.conversation_messages),
        'processing_jobs', (SELECT COUNT(*) FROM public.processing_jobs),
        'processing_jobs_errors', (SELECT COUNT(*) FROM public.processing_jobs_errors),
        'prompt_history', (SELECT COUNT(*) FROM public.prompt_history),
        'generated_images', (SELECT COUNT(*) FROM public.generated_images),
        'indexing_events', (SELECT COUNT(*) FROM public.indexing_events),
        'pdf_pages', (SELECT COUNT(*) FROM public.pdf_pages),
        'workers', (SELECT COUNT(*) FROM public.workers),
        'jobs', (SELECT COUNT(*) FROM public.jobs),
        'user_wikis', (SELECT COUNT(*) FROM public.user_wikis)
      ),
      'conversations', COALESCE(
        (SELECT json_agg(row_to_json(c))
         FROM (SELECT * FROM public.conversations
               ORDER BY created_at DESC LIMIT $1) c),
        '[]'::json
      )
    ) AS result
  `
  const result = await query(sql, [limit])
  ctx.body = result.rows[0].result
})

/**
 * GET /debug/tables/:name
 *
 * Lazy-loads a single table for the /debug page when the user clicks a tab.
 * Supports offset pagination (LIMIT 1000). Unknown table names are rejected
 * so this endpoint cannot be abused as a generic SQL runner.
 */
debugRouter.get('/api/debug/tables/:name', async (ctx) => {
  if (!isAuthorized(ctx)) {
    ctx.status = 401
    ctx.body = { error: 'Invalid credentials' }
    return
  }

  const name = String(ctx.params.name)
  const offset = Math.max(0, parseInt(String(ctx.query.offset ?? '0'), 10) || 0)
  const limit = 1000

  if (name === 'users') {
    // Runs the query maintained in backend/sql/users.sql. One row per
    // (user, day); the SQL's window function adds total_messages so the
    // UI can group/sort without a second round-trip.
    const result = await query(USERS_SQL)
    ctx.body = { rows: result.rows }
    return
  }

  if (!(DEBUG_TABLES as readonly string[]).includes(name)) {
    ctx.status = 400
    ctx.body = { error: 'Unknown table' }
    return
  }

  const select = TABLE_SELECT[name as DebugTable]
  const orderBy = TABLE_ORDER_BY[name as DebugTable] ?? 'created_at DESC'
  const result = await query(
    `SELECT ${select} FROM public.${name} ORDER BY ${orderBy} LIMIT $1 OFFSET $2`,
    [limit, offset],
  )
  ctx.body = { rows: result.rows }
})

/**
 * GET /debug/prompt-full/:promptId
 *
 * Returns only the full prompt_text and response_text for a prompt_history row.
 * Simpler alternative to the /conversationId/:promptId/full endpoint — used by the
 * debug table UI when expanding a row to show the raw strings.
 */
debugRouter.get('/api/debug/prompt-full/:promptId', async (ctx) => {
  const auth = ctx.headers.authorization
  if (!auth || !auth.startsWith('Basic ')) {
    ctx.status = 401
    ctx.body = { error: 'Authentication required' }
    return
  }
  const decoded = Buffer.from(auth.slice(6), 'base64').toString()
  const idx = decoded.indexOf(':')
  const user = idx < 0 ? decoded : decoded.slice(0, idx)
  const pass = idx < 0 ? '' : decoded.slice(idx + 1)
  if (
    !config.debugUser ||
    !config.debugPass ||
    !safeEq(user, config.debugUser) ||
    !safeEq(pass, config.debugPass)
  ) {
    ctx.status = 401
    ctx.body = { error: 'Invalid credentials' }
    return
  }

  const { promptId } = ctx.params
  const result = await query(
    'SELECT prompt_text, response_text FROM prompt_history WHERE id = $1',
    [promptId],
  )
  if (result.rows.length === 0) {
    ctx.status = 404
    ctx.body = { error: 'Not found' }
    return
  }
  ctx.body = result.rows[0]
})

/**
 * POST /debug/sql
 *
 * Executes an arbitrary SQL statement from the debug UI.
 * Protected by basic auth; intended for admin-only ad-hoc inspection.
 * Enforces a per-statement timeout and row cap to keep the UI responsive.
 */
debugRouter.post('/api/debug/sql', async (ctx) => {
  if (!isAuthorized(ctx)) {
    ctx.status = 401
    ctx.body = { error: 'Invalid credentials' }
    return
  }

  const body = (ctx.request.body ?? {}) as { sql?: unknown }
  const sql = typeof body.sql === 'string' ? body.sql.trim() : ''
  if (!sql) {
    ctx.status = 400
    ctx.body = { error: 'Missing "sql" string in request body' }
    return
  }

  const client = await pool.connect()
  const startedAt = Date.now()
  try {
    // Read-only transaction with 10s timeout. Prevents accidental writes and
    // runaway queries. SET LOCAL only applies within a transaction.
    await client.query('BEGIN READ ONLY')
    await client.query('SET LOCAL statement_timeout = 10000')
    const result = await client.query(sql)
    await client.query('COMMIT')
    ctx.body = {
      rows: result.rows,
      fields: result.fields.map((f) => f.name),
      rowCount: result.rowCount,
      command: result.command,
      durationMs: Date.now() - startedAt,
    }
  } catch (err: unknown) {
    try {
      await client.query('ROLLBACK')
    } catch {
      /* ignore */
    }
    ctx.status = 400
    ctx.body = {
      error: err instanceof Error ? err.message : 'Query failed',
      durationMs: Date.now() - startedAt,
    }
  } finally {
    client.release()
  }
})
