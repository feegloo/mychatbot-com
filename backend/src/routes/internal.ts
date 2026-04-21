/**
 * Internal cross-instance endpoint for delegating CPU-heavy PDF indexing.
 *
 * POST /internal/index-stream
 *   Accepts an indexing job from another Cloud Run instance, processes it using
 *   the local Python server, and streams NDJSON events back to the caller.
 *
 * Security: requests must carry the X-Indexer-Secret header matching INDEXER_SECRET.
 * In production the chatrag-indexer service is deployed with --ingress internal-and-cloud-load-balancing
 * so only VPC-internal callers (main chatrag service) can reach it.
 */
import Router from '@koa/router'
import { timingSafeEqual } from 'node:crypto'
import { config } from '../config.js'
import { indexConversationStream } from '../python/indexing.js'
import logger from '../logger.js'

export const internalRouter = new Router()

internalRouter.post('/internal/index-stream', async (ctx) => {
  if (!authenticateSecret(ctx.headers['x-indexer-secret'])) {
    ctx.status = 401
    ctx.body = { error: 'Unauthorized' }
    return
  }

  const { conversationId, collectionName, files } = ctx.request.body as {
    conversationId?: string
    collectionName?: string
    files?: string[]
  }

  if (!conversationId || !collectionName || !Array.isArray(files)) {
    ctx.status = 400
    ctx.body = { error: 'Missing required fields: conversationId, collectionName, files' }
    return
  }

  logger.info({ conversationId, fileCount: files.length }, 'Delegated indexing job received')

  // Stream NDJSON directly — bypass Koa's automatic response handling
  ctx.respond = false
  ctx.res.setHeader('Content-Type', 'application/x-ndjson')
  ctx.res.setHeader('Transfer-Encoding', 'chunked')
  ctx.res.writeHead(200)

  try {
    for await (const event of indexConversationStream({ conversationId, collectionName, files })) {
      ctx.res.write(JSON.stringify(event) + '\n')
    }
  } catch (err: any) {
    logger.error({ err, conversationId }, 'Delegated indexing failed')
    ctx.res.write(JSON.stringify({ event: 'error', data: { error: err.message } }) + '\n')
  } finally {
    ctx.res.end()
  }
})

// Health check for the indexer role — caller can verify the service is ready
internalRouter.get('/internal/health', (ctx) => {
  ctx.body = { ok: true, role: 'indexer' }
})

function authenticateSecret(header: string | string[] | undefined): boolean {
  if (!config.indexerSecret) {
    // If no secret configured, reject all internal calls (fail-safe)
    return false
  }
  const incoming = Array.isArray(header) ? header[0] : header
  if (!incoming) return false
  try {
    const expected = Buffer.from(config.indexerSecret)
    const actual = Buffer.from(incoming)
    if (expected.length !== actual.length) return false
    return timingSafeEqual(expected, actual)
  } catch {
    return false
  }
}
