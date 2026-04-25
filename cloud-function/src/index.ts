import { http, type HttpFunction } from '@google-cloud/functions-framework'
import * as Sentry from '@sentry/node'

const DEFAULT_ALLOWED_ORIGINS = ['https://chatrag.app', 'https://www.chatrag.app']
const DEFAULT_UPSTREAM_UPLOAD_URL = 'https://chatrag.app/api/upload'
const DEFAULT_PUBLIC_APP_BASE_URL = 'https://chatrag.app'

const allowedOrigins = new Set(
  (process.env.ALLOWED_ORIGINS || DEFAULT_ALLOWED_ORIGINS.join(','))
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean),
)

const upstreamUploadUrl = process.env.UPSTREAM_UPLOAD_URL || DEFAULT_UPSTREAM_UPLOAD_URL
const publicAppBaseUrl = process.env.PUBLIC_APP_BASE_URL || DEFAULT_PUBLIC_APP_BASE_URL

Sentry.init({
  dsn: process.env.SENTRY_DSN,
  environment: process.env.SENTRY_ENVIRONMENT || 'dev',
  tracesSampleRate: 1.0,
  enableLogs: true,
})

function applyCors(req: Parameters<HttpFunction>[0], res: Parameters<HttpFunction>[1]) {
  const origin = req.get('origin')
  if (origin && allowedOrigins.has(origin)) {
    res.set('Access-Control-Allow-Origin', origin)
    res.set('Vary', 'Origin')
  }

  res.set('Access-Control-Allow-Methods', 'POST, OPTIONS')
  res.set(
    'Access-Control-Allow-Headers',
    'Content-Type, Authorization, X-Conversation-Token, X-Trace-Id, sentry-trace, baggage',
  )
  res.set('Access-Control-Max-Age', '3600')
}

function normalizeConversationUrl(rawPathOrUrl: unknown, conversationId: unknown): string | null {
  if (typeof conversationId === 'string' && conversationId.length > 0) {
    return `${publicAppBaseUrl.replace(/\/$/, '')}/c/${conversationId}`
  }

  if (typeof rawPathOrUrl !== 'string' || rawPathOrUrl.length === 0) {
    return null
  }

  try {
    return new URL(rawPathOrUrl, publicAppBaseUrl).toString()
  } catch {
    return null
  }
}

function isSupportedPath(path: string): boolean {
  return path === '/' || path === '/upload'
}

export const uploadProxy: HttpFunction = async (req, res) => {
  applyCors(req, res)

  const traceId = req.get('x-trace-id') || ''
  const sentryTrace = req.get('sentry-trace') || ''
  const baggage = req.get('baggage') || ''
  if (traceId) {
    res.set('X-Trace-Id', traceId)
  }

  if (req.method === 'OPTIONS') {
    res.status(204).send('')
    return
  }

  if (req.method !== 'POST') {
    res.status(405).json({ error: 'Method not allowed' })
    return
  }

  if (!isSupportedPath(req.path)) {
    res.status(404).json({ error: 'Not found' })
    return
  }

  const contentType = req.get('content-type') || ''
  if (!contentType.toLowerCase().includes('multipart/form-data')) {
    res.status(400).json({ error: 'Expected multipart/form-data upload' })
    return
  }

  const headers = new Headers()
  headers.set('content-type', contentType)
  if (traceId) {
    headers.set('x-trace-id', traceId)
  }
  if (sentryTrace) {
    headers.set('sentry-trace', sentryTrace)
  }
  if (baggage) {
    headers.set('baggage', baggage)
  }

  const token = req.get('x-conversation-token')
  if (token) {
    headers.set('x-conversation-token', token)
  }

  const authorization = req.get('authorization')
  if (authorization) {
    headers.set('authorization', authorization)
  }

  const rawBody = req.rawBody
  const bufferedBody = rawBody ? new Uint8Array(rawBody) : null

  const upstreamResponse = await Sentry.continueTrace({ sentryTrace, baggage }, async () => {
    return Sentry.startSpan(
      {
        name: 'cloud_function.upload_proxy',
        op: 'http.server',
        forceTransaction: true,
        attributes: {
          'chatrag.trace_id': traceId,
          'http.route': req.path,
        },
      },
      async () => {
        if (traceId) {
          Sentry.setTag('trace_id', traceId)
          Sentry.captureMessage(`Cloud Function accepted upload [${traceId}]`, 'debug')
        }

        const traceData = Sentry.getTraceData()
        if (traceData['sentry-trace']) {
          headers.set('sentry-trace', traceData['sentry-trace'])
        }
        if (traceData.baggage) {
          headers.set('baggage', traceData.baggage)
        }

        return fetch(upstreamUploadUrl, {
          method: 'POST',
          headers,
          body: bufferedBody ?? (req as unknown as BodyInit),
          ...(bufferedBody ? {} : { duplex: 'half' as const }),
        })
      },
    )
  })

  const responseText = await upstreamResponse.text()
  let upstreamPayload: Record<string, unknown> = {}
  try {
    upstreamPayload = JSON.parse(responseText) as Record<string, unknown>
  } catch {
    upstreamPayload = { raw: responseText }
  }

  if (!upstreamResponse.ok) {
    if (traceId) {
      Sentry.captureMessage(`Cloud Function upstream upload failed [${traceId}]`, 'error')
    }
    res.status(upstreamResponse.status).json({
      error: 'Upstream upload failed',
      upstream: upstreamPayload,
    })
    return
  }

  const conversationId = upstreamPayload.conversationId
  const conversationUrl = normalizeConversationUrl(upstreamPayload.url, conversationId)

  res.status(200).json({
    conversationId,
    url: conversationUrl,
    status: upstreamPayload.status || 'processing',
    ownerPassword: upstreamPayload.ownerPassword || null,
  })
}

http('uploadProxy', uploadProxy)
