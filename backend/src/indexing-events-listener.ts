/**
 * Dedicated Postgres LISTEN client that relays worker events to SSE.
 *
 * Architecture recap:
 *   Worker (chatrag-worker Cloud Run Worker Pool)
 *     → INSERT indexing_events
 *     → NOTIFY indexing_events <event_id>
 *   ALL backend (chatrag Cloud Run) instances
 *     → receive NOTIFY
 *     → claimIndexingEvent(id)        ← atomic; exactly one wins
 *     → handleIndexingEvent(row)
 *         → DB side-effects + emitConversationEvent()
 *         → emitConversationEvent is in-process: only the backend
 *           instance with the browser's SSE socket will forward to the
 *           client. All other instances no-op harmlessly.
 *
 * Startup safety: on connect we first drain any unprocessed events (rows
 * with processed_at IS NULL) so events that arrived while this instance
 * was starting up don't get missed. ``claimIndexingEvent`` dedup still
 * prevents double-processing if another replica already handled them.
 *
 * Reconnection: on network errors we backoff + reconnect. The catch-up
 * sweep runs again after each reconnect.
 */

import type { ClientConfig, Notification } from 'pg'
import pg from 'pg'

import { config } from './config.js'
import { claimIndexingEvent } from './indexing-jobs.js'
import { handleIndexingEvent } from './indexing-handler.js'

const { Client } = pg

const CHANNEL = 'indexing_events'
const RECONNECT_INITIAL_MS = 1_000
const RECONNECT_MAX_MS = 30_000

let client: pg.Client | null = null
let stopped = false
let reconnectDelay = RECONNECT_INITIAL_MS
let reconnectTimer: NodeJS.Timeout | null = null

/**
 * Boot the listener. Idempotent; repeated calls are no-ops while a
 * connection is live. Call this from the app's startup hook when
 * ``config.workerMode === 'cloud_run'``. In 'inline' mode it's unused.
 */
export async function startIndexingEventsListener(): Promise<void> {
  if (config.workerMode !== 'cloud_run') {
    return
  }
  if (client) return
  stopped = false
  await connect()
}

export async function stopIndexingEventsListener(): Promise<void> {
  stopped = true
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (client) {
    try {
      await client.end()
    } catch {
      // ignore
    }
    client = null
  }
}

async function connect(): Promise<void> {
  const clientConfig: ClientConfig = {
    connectionString: config.databaseUrl,
  }
  const next = new Client(clientConfig)
  next.on('error', handleClientError)
  next.on('notification', handleNotification)

  try {
    await next.connect()
    await next.query(`LISTEN ${CHANNEL}`)
    client = next
    reconnectDelay = RECONNECT_INITIAL_MS
    console.log(`[indexing-listener] LISTEN ${CHANNEL} ready`)
    // Catch up on anything emitted while we weren't listening.
    await drainUnprocessed()
  } catch (err) {
    console.error('[indexing-listener] connect failed:', (err as Error).message)
    scheduleReconnect()
  }
}

function handleClientError(err: Error): void {
  console.error('[indexing-listener] client error:', err.message)
  // pg will not auto-reconnect; we have to rebuild the client.
  if (client) {
    const dying = client
    client = null
    dying.end().catch(() => {})
  }
  scheduleReconnect()
}

function scheduleReconnect(): void {
  if (stopped || reconnectTimer) return
  const delay = reconnectDelay
  reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS)
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    if (!stopped) void connect()
  }, delay)
}

function handleNotification(notification: Notification): void {
  if (notification.channel !== CHANNEL) return
  const raw = notification.payload
  if (!raw) return
  const eventId = Number(raw)
  if (!Number.isFinite(eventId) || eventId <= 0) {
    console.warn('[indexing-listener] bad payload:', raw)
    return
  }
  // Fire-and-forget; failures are logged inside processEvent.
  void processEvent(eventId)
}

async function processEvent(eventId: number): Promise<void> {
  try {
    const event = await claimIndexingEvent(eventId)
    if (!event) {
      // Another backend replica beat us to it. Normal in multi-instance
      // deployments; not an error.
      return
    }
    await handleIndexingEvent(event)
  } catch (err) {
    console.error(
      `[indexing-listener] processEvent(${eventId}) failed:`,
      (err as Error).message,
    )
  }
}

/**
 * Catch-up scan: process all events whose ``processed_at`` is still NULL.
 * Runs at startup (and after every reconnect) so events emitted while
 * this backend was down don't get orphaned — NOTIFY is fire-and-forget
 * and is not re-delivered on reconnect.
 *
 * Uses LIMIT + loop rather than one giant query so we don't blow up on
 * a backlog of thousands of events (unlikely but cheap insurance).
 */
async function drainUnprocessed(): Promise<void> {
  const BATCH = 100
  while (!stopped) {
    const rows = await pickUnprocessedBatch(BATCH)
    if (rows.length === 0) return
    for (const id of rows) {
      await processEvent(id)
    }
    if (rows.length < BATCH) return
  }
}

async function pickUnprocessedBatch(limit: number): Promise<number[]> {
  if (!client) return []
  const res = await client.query<{ id: string }>(
    `SELECT id FROM indexing_events
      WHERE processed_at IS NULL
      ORDER BY id ASC
      LIMIT $1`,
    [limit],
  )
  return res.rows.map((r) => Number(r.id))
}
