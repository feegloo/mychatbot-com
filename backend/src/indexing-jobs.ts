/**
 * Indexing pipeline glue between the upload route and the chatrag-worker
 * Cloud Run service.
 *
 * Two responsibilities live here:
 *
 * 1. **Publish** new indexing jobs to the GCP Pub/Sub topic
 *    ``chatrag-indexing``. The worker pulls from
 *    ``chatrag-indexing-sub`` and runs ``index_documents`` on its own
 *    pod, then writes progress events back to ``indexing_events``.
 *
 * 2. **Claim/replay** worker-emitted events from ``indexing_events``.
 *    ``claimIndexingEvent`` is the cross-replica single-writer guarantee
 *    used by ``indexing-events-listener.ts``. ``getEventsSince`` powers
 *    browser-reconnect replay.
 *
 * There is no jobs table any more — Pub/Sub owns the queue. The worker
 * embeds its job UUID and per-job metadata directly in the JSONB
 * ``payload`` column so the backend handler can correlate without
 * touching another table.
 */

import { PubSub, type Topic } from '@google-cloud/pubsub'
import { config } from './config.js'
import { query } from './db.js'

export type PublishIndexingJobInput = {
  conversationId: string
  collectionName: string
  /**
   * Each entry is either:
   *   - a local absolute path (single-machine dev), or
   *   - a ``gs://bucket/key`` URI, or
   *   - a ``<local>|gs://...`` pair so the worker tries the local file
   *     first and falls back to GCS download.
   */
  filePaths: string[]
  storageNamespace?: string | null
  metadata?: Record<string, unknown>
}

export class PubSubNotConfigured extends Error {
  constructor() {
    super(
      'Pub/Sub is not configured: set PUBSUB_TOPIC (and GOOGLE_APPLICATION_CREDENTIALS or run on GCP)',
    )
    this.name = 'PubSubNotConfigured'
  }
}

let _client: PubSub | null = null
let _topic: Topic | null = null

function getTopic(): Topic {
  const topicName = config.pubsubTopic
  if (!topicName) throw new PubSubNotConfigured()
  if (!_client) _client = new PubSub({ projectId: config.gcpProjectId || undefined })
  if (!_topic) _topic = _client.topic(topicName)
  return _topic
}

/**
 * Publish a new indexing job. Resolves with the Pub/Sub message id once
 * the publish RPC completes (sub-second on a warm client).
 *
 * The payload shape mirrors ``python/shared/pubsub_client.py`` so the
 * Python ``IndexingJobPayload.from_json`` parser can decode it without
 * special-casing the producer.
 */
export async function publishIndexingJob(
  input: PublishIndexingJobInput,
): Promise<string> {
  if (input.filePaths.length === 0) {
    throw new Error('publishIndexingJob: filePaths must not be empty')
  }
  const payload = {
    workerName: 'chatrag-backend',
    fileName: input.filePaths,
    conversationId: input.conversationId,
    collectionName: input.collectionName,
    jobId: cryptoRandomId(),
    storageNamespace: input.storageNamespace ?? null,
    metadata: input.metadata ?? {},
  }
  const data = Buffer.from(JSON.stringify(payload), 'utf8')
  return getTopic().publishMessage({ data })
}

/**
 * Atomically claim one event row, returning null if another backend
 * replica already processed it. The ``processed_at`` flip is the
 * exactly-once guarantee for handlers that have side-effects (welcome
 * message insert, status update, SSE emit).
 */
export async function claimIndexingEvent(
  eventId: number,
): Promise<{
  id: number
  conversation_id: string
  event_type: string
  payload: Record<string, unknown>
} | null> {
  const result = await query(
    `UPDATE indexing_events
        SET processed_at = NOW()
      WHERE id = $1 AND processed_at IS NULL
      RETURNING id, conversation_id, event_type, payload`,
    [eventId],
  )
  if (result.rows.length === 0) return null
  const row = result.rows[0]
  return {
    id: Number(row.id),
    conversation_id: row.conversation_id,
    event_type: row.event_type,
    payload: row.payload ?? {},
  }
}

/**
 * Replay events after a given id for a conversation. Used by browsers
 * that reconnect mid-indexing and need to catch up on progress emitted
 * while disconnected. ``sinceId`` of 0 returns every event ever persisted.
 */
export async function getEventsSince(
  conversationId: string,
  sinceId: number,
  limit = 500,
): Promise<
  Array<{
    id: number
    event_type: string
    payload: Record<string, unknown>
  }>
> {
  const result = await query(
    `SELECT id, event_type, payload
       FROM indexing_events
      WHERE conversation_id = $1 AND id > $2
   ORDER BY id ASC
      LIMIT $3`,
    [conversationId, sinceId, limit],
  )
  return result.rows.map((row: any) => ({
    id: Number(row.id),
    event_type: row.event_type,
    payload: row.payload ?? {},
  }))
}

function cryptoRandomId(): string {
  // Cheap UUIDv4 without pulling another dep — only used as a correlation
  // id surfaced in Sentry/logs; not security-sensitive.
  const bytes = new Uint8Array(16)
  for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256)
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
