import Router from '@koa/router'
import { timingSafeEqual } from 'node:crypto'
import { query } from '../db.js'
import { config } from '../config.js'

function safeEq(a: string, b: string): boolean {
  const bufA = Buffer.from(a)
  const bufB = Buffer.from(b)
  if (bufA.length !== bufB.length) return false
  return timingSafeEqual(bufA, bufB)
}

export const debugRouter = new Router()

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
    promptHistory,
  ] = await Promise.all([
    query('SELECT * FROM public.conversations ORDER BY created_at DESC LIMIT $1 OFFSET $2', [
      limit,
      offset,
    ]),
    query(
      `SELECT id, conversation_id, role, LEFT(content, 500) AS content, model,
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
      `SELECT id, conversation_id, operation, model,
              LEFT(prompt_text, 2000) AS prompt_text,
              LENGTH(prompt_text) AS prompt_chars,
              LEFT(response_text, 2000) AS response_text,
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
           LENGTH(prompt_text) AS prompt_chars,
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
