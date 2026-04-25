import type { Context, Next } from 'koa'
import { randomUUID } from 'node:crypto'
import * as Sentry from '@sentry/node'
import logger from '../logger.js'
import { TRACE_ID_HEADER } from '../constants.js'

const HEADER = 'x-request-id'

/**
 * Tags every API request with a stable id so the same identifier can be
 * grepped across browser → Node → Python logs and matched to the Sentry
 * trace. Respects a client-provided id, otherwise mints a fresh UUID.
 */
export async function requestIdMiddleware(ctx: Context, next: Next) {
  const incoming = ctx.get(HEADER)
  const requestId = incoming && incoming.length <= 80 ? incoming : randomUUID()
  const incomingTraceId = ctx.get(TRACE_ID_HEADER)
  const traceId = incomingTraceId && incomingTraceId.length <= 64 ? incomingTraceId : ''
  ctx.state.requestId = requestId
  ctx.state.traceId = traceId
  ctx.set('X-Request-Id', requestId)
  if (traceId) {
    ctx.set('X-Trace-Id', traceId)
  }

  Sentry.getCurrentScope().setTag('request_id', requestId)
  if (traceId) {
    Sentry.getCurrentScope().setTag('trace_id', traceId)
  }
  ctx.state.log = logger.child({ requestId, traceId: traceId || undefined })
  await next()
}

export function getRequestId(ctx: Context): string {
  return (ctx.state.requestId as string | undefined) || ''
}

export function getTraceId(ctx: Context): string {
  return (ctx.state.traceId as string | undefined) || ''
}

/**
 * While awaiting a long operation, emit a log line every `intervalMs` so a
 * stuck call (e.g. OpenAI not responding) is visible in Cloud Run logs
 * before the client-side timeout fires. Returns a clear function you must
 * call in a `finally` block.
 */
export function startHeartbeat(
  label: string,
  meta: Record<string, unknown>,
  intervalMs = 10_000,
): () => void {
  const started = Date.now()
  const timer = setInterval(() => {
    const elapsedMs = Date.now() - started
    logger.warn({ ...meta, elapsedMs, label }, `⏳ [heartbeat] ${label} still waiting`)
  }, intervalMs)
  return () => clearInterval(timer)
}
