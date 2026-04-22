import Router from '@koa/router'
import { timingSafeEqual } from 'node:crypto'
import { pool, query } from '../db.js'
import { config } from '../config.js'

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
}

/**
 * GET /debug/tables-overview
 *
 * Single-round-trip endpoint for the /debug page's initial load.
 * Returns row counts for every table (for the tab badges) plus the first
 * page of the `conversations` table (the default active tab) in ONE SQL
 * statement via a CTE with json_build_object. Lazy-loads everything else.
 */
debugRouter.get('/debug/tables-overview', async (ctx) => {
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
        'prompt_history', (SELECT COUNT(*) FROM public.prompt_history)
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
debugRouter.get('/debug/tables/:name', async (ctx) => {
  if (!isAuthorized(ctx)) {
    ctx.status = 401
    ctx.body = { error: 'Invalid credentials' }
    return
  }

  const name = String(ctx.params.name)
  const offset = Math.max(0, parseInt(String(ctx.query.offset ?? '0'), 10) || 0)
  const limit = 1000

  if (name === 'users') {
    const result = await query(
      `SELECT cm.user_id, uf.fingerprint, COUNT(*) AS message_count,
              MIN(cm.created_at) AS first_seen, MAX(cm.created_at) AS last_seen
       FROM public.conversation_messages cm
       LEFT JOIN public.user_fingerprints uf ON uf.user_id = cm.user_id
       GROUP BY cm.user_id, uf.fingerprint
       ORDER BY message_count DESC`,
    )
    ctx.body = { rows: result.rows }
    return
  }

  if (!(DEBUG_TABLES as readonly string[]).includes(name)) {
    ctx.status = 400
    ctx.body = { error: 'Unknown table' }
    return
  }

  const select = TABLE_SELECT[name as DebugTable]
  const result = await query(
    `SELECT ${select} FROM public.${name} ORDER BY created_at DESC LIMIT $1 OFFSET $2`,
    [limit, offset],
  )
  ctx.body = { rows: result.rows }
})

debugRouter.get('/debug/tables', async (ctx) => {
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

  const offset = Math.max(0, parseInt(String(ctx.query.offset ?? '0'), 10) || 0)
  const limit = 1000

  const [
    conversations,
    messages,
    suggestedQuestions,
    uploadedFiles,
    userFingerprints,
    conversationAccessTokens,
    accessRequests,
    users,
    processingJobs,
    processingJobsErrors,
    promptHistory,
  ] = await Promise.all([
    query('SELECT * FROM public.conversations ORDER BY created_at DESC LIMIT $1 OFFSET $2', [
      limit,
      offset,
    ]),
    query(
      `SELECT id, conversation_id, role, LEFT(content, 500) AS content,
              created_at, user_id
       FROM public.conversation_messages ORDER BY created_at DESC LIMIT $1 OFFSET $2`,
      [limit, offset],
    ),
    query('SELECT * FROM public.suggested_questions ORDER BY created_at DESC LIMIT $1 OFFSET $2', [
      limit,
      offset,
    ]),
    query('SELECT * FROM public.uploaded_files ORDER BY created_at DESC LIMIT $1 OFFSET $2', [
      limit,
      offset,
    ]),
    query('SELECT * FROM public.user_fingerprints ORDER BY created_at DESC LIMIT $1 OFFSET $2', [
      limit,
      offset,
    ]),
    query(
      'SELECT * FROM public.conversation_access_tokens ORDER BY created_at DESC LIMIT $1 OFFSET $2',
      [limit, offset],
    ),
    query('SELECT * FROM public.access_requests ORDER BY created_at DESC LIMIT $1 OFFSET $2', [
      limit,
      offset,
    ]),
    query(`SELECT cm.user_id, uf.fingerprint, COUNT(*) AS message_count,
                  MIN(cm.created_at) AS first_seen, MAX(cm.created_at) AS last_seen
           FROM public.conversation_messages cm
           LEFT JOIN public.user_fingerprints uf ON uf.user_id = cm.user_id
           GROUP BY cm.user_id, uf.fingerprint
           ORDER BY message_count DESC`),
    query('SELECT * FROM public.processing_jobs ORDER BY created_at DESC LIMIT $1 OFFSET $2', [
      limit,
      offset,
    ]),
    query(
      `SELECT id, uid, processing_job_id, conversation_id, file_name,
              page_number, step, content_type,
              LEFT(content, 500) AS content,
              LENGTH(content) AS content_chars,
              image_path, error_type,
              LEFT(error_message, 500) AS error_message,
              LENGTH(error_message) AS error_chars,
              worker_id, retry_count, created_at
       FROM public.processing_jobs_errors
       ORDER BY created_at DESC LIMIT $1 OFFSET $2`,
      [limit, offset],
    ),
    query(
      `SELECT id, conversation_id, operation, model,
              LEFT(prompt_text, 300) AS prompt_text,
              LENGTH(prompt_text) AS prompt_chars,
              LEFT(response_text, 300) AS response_text,
              LENGTH(response_text) AS response_chars,
              prompt_tokens, completion_tokens, total_tokens, cached_tokens,
              duration_ms, created_at
       FROM public.prompt_history ORDER BY created_at DESC LIMIT $1 OFFSET $2`,
      [limit, offset],
    ),
  ])

  ctx.body = {
    conversations: conversations.rows,
    conversation_messages: messages.rows,
    suggested_questions: suggestedQuestions.rows,
    uploaded_files: uploadedFiles.rows,
    user_fingerprints: userFingerprints.rows,
    conversation_access_tokens: conversationAccessTokens.rows,
    access_requests: accessRequests.rows,
    users: users.rows,
    processing_jobs: processingJobs.rows,
    processing_jobs_errors: processingJobsErrors.rows,
    prompt_history: promptHistory.rows,
  }
})

/**
 * GET /debug/processing-jobs
 * GET /debug/processing-jobs/:conversationId
 *
 * Live view of file/page processing telemetry.
 * Shows all steps with timestamps, durations, errors, worker IDs.
 */
async function handleProcessingJobs(ctx: any) {
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

  const conversationId = ctx.params.conversationId
  const limit = Math.min(parseInt(String(ctx.query.limit ?? '500'), 10) || 500, 5000)
  const statusFilter = ctx.query.status as string | undefined

  let sql = `
    SELECT id, conversation_id, file_name, page_number, total_pages,
           status, step, detail, error_message, retry_count,
           duration_ms, worker_id, started_at, completed_at, created_at
    FROM processing_jobs
  `
  const params: any[] = []
  const conditions: string[] = []

  if (conversationId) {
    conditions.push(`conversation_id = $${params.length + 1}`)
    params.push(conversationId)
  }
  if (statusFilter) {
    conditions.push(`status = $${params.length + 1}`)
    params.push(statusFilter)
  }

  if (conditions.length > 0) {
    sql += ` WHERE ${conditions.join(' AND ')}`
  }
  sql += ` ORDER BY created_at DESC LIMIT $${params.length + 1}`
  params.push(limit)

  const jobs = await query(sql, params)

  // Summary stats
  const summaryResult = await query(
    `
    SELECT
      status,
      COUNT(*) as count,
      AVG(duration_ms) as avg_duration_ms,
      MAX(duration_ms) as max_duration_ms,
      MIN(duration_ms) as min_duration_ms
    FROM processing_jobs
    ${conversationId ? 'WHERE conversation_id = $1' : ''}
    GROUP BY status
    ORDER BY status
  `,
    conversationId ? [conversationId] : [],
  )

  // Recent conversations with jobs
  const recentConversations = await query(`
    SELECT conversation_id,
           COUNT(*) as job_count,
           COUNT(*) FILTER (WHERE status = 'completed') as completed,
           COUNT(*) FILTER (WHERE status = 'failed') as failed,
           COUNT(*) FILTER (WHERE status = 'running') as running,
           MIN(created_at) as first_job,
           MAX(created_at) as last_job,
           AVG(duration_ms) FILTER (WHERE duration_ms IS NOT NULL) as avg_duration_ms
    FROM processing_jobs
    GROUP BY conversation_id
    ORDER BY last_job DESC
    LIMIT 20
  `)

  ctx.body = {
    jobs: jobs.rows,
    summary: summaryResult.rows,
    recent_conversations: recentConversations.rows,
    total: jobs.rows.length,
    limit,
  }
}

debugRouter.get('/debug/processing-jobs', handleProcessingJobs)
debugRouter.get('/debug/processing-jobs/:conversationId', handleProcessingJobs)

/**
 * GET /debug/processing-jobs-errors
 * GET /debug/processing-jobs-errors/:conversationId
 * GET /debug/processing-jobs-errors/uid/:uid
 *
 * Per-failure error rows with the text/image snapshot that caused the error.
 * Lets us debug hundreds of per-page errors from a single large PDF.
 */
async function handleProcessingJobsErrors(ctx: any) {
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

  const uid = ctx.params.uid as string | undefined
  const conversationId = ctx.params.conversationId as string | undefined
  const limit = Math.min(parseInt(String(ctx.query.limit ?? '500'), 10) || 500, 5000)
  const step = ctx.query.step as string | undefined

  if (uid) {
    // Return full row (with full content + stack_trace) for a single error.
    const row = await query(
      'SELECT * FROM public.processing_jobs_errors WHERE uid = $1 LIMIT 1',
      [uid],
    )
    ctx.body = { error: row.rows[0] || null }
    return
  }

  const params: any[] = []
  const conditions: string[] = []
  if (conversationId) {
    conditions.push(`conversation_id = $${params.length + 1}`)
    params.push(conversationId)
  }
  if (step) {
    conditions.push(`step = $${params.length + 1}`)
    params.push(step)
  }

  let sql = `
    SELECT id, uid, processing_job_id, conversation_id, file_name,
           page_number, step, content_type,
           LEFT(content, 500) AS content,
           LENGTH(content) AS content_chars,
           image_path, error_type,
           LEFT(error_message, 500) AS error_message,
           LENGTH(error_message) AS error_chars,
           worker_id, retry_count, created_at
    FROM public.processing_jobs_errors
  `
  if (conditions.length > 0) sql += ` WHERE ${conditions.join(' AND ')}`
  sql += ` ORDER BY created_at DESC LIMIT $${params.length + 1}`
  params.push(limit)

  const rows = await query(sql, params)

  const byStep = await query(
    `SELECT step, error_type, COUNT(*) AS count
     FROM public.processing_jobs_errors
     ${conversationId ? 'WHERE conversation_id = $1' : ''}
     GROUP BY step, error_type
     ORDER BY count DESC
     LIMIT 50`,
    conversationId ? [conversationId] : [],
  )

  ctx.body = {
    errors: rows.rows,
    summary: byStep.rows,
    total: rows.rows.length,
    limit,
  }
}

debugRouter.get('/debug/processing-jobs-errors', handleProcessingJobsErrors)
debugRouter.get('/debug/processing-jobs-errors/uid/:uid', handleProcessingJobsErrors)
debugRouter.get(
  '/debug/processing-jobs-errors/:conversationId',
  handleProcessingJobsErrors,
)

/**
 * GET /debug/prompt-history
 * GET /debug/prompt-history/:conversationId
 *
 * View LLM prompt/response history with token usage and timing.
 */
async function handlePromptHistory(ctx: any) {
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

  const conversationId = ctx.params.conversationId
  const limit = Math.min(parseInt(String(ctx.query.limit ?? '100'), 10) || 100, 1000)
  const operation = ctx.query.operation as string | undefined

  let sql = `
    SELECT id, conversation_id, operation, model,
           LEFT(prompt_text, 300) AS prompt_text,
           LENGTH(prompt_text) AS prompt_chars,
           LEFT(response_text, 300) AS response_text,
           LENGTH(response_text) AS response_chars,
           prompt_tokens, completion_tokens, total_tokens, cached_tokens,
           duration_ms, created_at
    FROM prompt_history
  `
  const params: any[] = []
  const conditions: string[] = []

  if (conversationId) {
    conditions.push(`conversation_id = $${params.length + 1}`)
    params.push(conversationId)
  }
  if (operation) {
    conditions.push(`operation = $${params.length + 1}`)
    params.push(operation)
  }
  if (conditions.length > 0) {
    sql += ` WHERE ${conditions.join(' AND ')}`
  }
  sql += ` ORDER BY created_at DESC LIMIT $${params.length + 1}`
  params.push(limit)

  const rows = await query(sql, params)

  // Summary by operation
  const summaryResult = await query(
    `SELECT operation, model,
            COUNT(*) AS call_count,
            AVG(duration_ms) AS avg_duration_ms,
            MAX(duration_ms) AS max_duration_ms,
            SUM(prompt_tokens) AS total_prompt_tokens,
            SUM(completion_tokens) AS total_completion_tokens,
            SUM(total_tokens) AS total_tokens,
            SUM(cached_tokens) AS total_cached_tokens
     FROM prompt_history
     ${conversationId ? 'WHERE conversation_id = $1' : ''}
     GROUP BY operation, model
     ORDER BY call_count DESC`,
    conversationId ? [conversationId] : [],
  )

  ctx.body = {
    prompts: rows.rows,
    summary: summaryResult.rows,
    total: rows.rows.length,
    limit,
  }
}

debugRouter.get('/debug/prompt-history', handlePromptHistory)
debugRouter.get('/debug/prompt-history/:conversationId', handlePromptHistory)

/**
 * GET /debug/prompt-history/:conversationId/:promptId/full
 *
 * View full prompt/response text for a specific prompt_history row.
 */
debugRouter.get('/debug/prompt-history/:conversationId/:promptId/full', async (ctx) => {
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
  const result = await query('SELECT * FROM prompt_history WHERE id = $1', [promptId])
  if (result.rows.length === 0) {
    ctx.status = 404
    ctx.body = { error: 'Prompt not found' }
    return
  }
  ctx.body = result.rows[0]
})

/**
 * GET /debug/prompt-full/:promptId
 *
 * Returns only the full prompt_text and response_text for a prompt_history row.
 * Simpler alternative to the /conversationId/:promptId/full endpoint — used by the
 * debug table UI when expanding a row to show the raw strings.
 */
debugRouter.get('/debug/prompt-full/:promptId', async (ctx) => {
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
debugRouter.post('/debug/sql', async (ctx) => {
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
