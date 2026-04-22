/**
 * Enqueue + observe helpers for the indexing_jobs queue.
 *
 * Workers on the chatrag-indexer Cloud Run service claim rows from this
 * table (see python/shared/job_queue.py). This module is the backend's
 * *producer* side — it inserts jobs and looks them up for `/upload`
 * responses. Actual claim/heartbeat/complete logic lives in Python.
 *
 * Schema is owned by backend/sql/013-indexing-jobs.sql and auto-bootstrapped
 * in db.ts; this file never issues DDL.
 */

import { query } from './db.js'

export type EnqueueIndexingJobInput = {
  conversationId: string
  collectionName: string
  /**
   * Either local absolute paths (single-node dev) or gs:// URIs. The
   * worker's _ensure_files_local resolves both shapes.
   */
  filePaths: string[]
  storageNamespace?: string | null
  metadata?: Record<string, unknown>
  maxAttempts?: number
}

export type IndexingJobRow = {
  id: number
  conversation_id: string
  collection_name: string
  file_paths: string[]
  storage_namespace: string | null
  status: 'queued' | 'claimed' | 'running' | 'done' | 'error'
  claimed_by: string | null
  attempts: number
  max_attempts: number
  error_message: string | null
  created_at: Date
  finished_at: Date | null
}

/**
 * Insert a job; the AFTER INSERT trigger fires NOTIFY indexing_jobs_new
 * so any worker LISTEN'ing wakes immediately. Returns the new job id.
 */
export async function enqueueIndexingJob(
  input: EnqueueIndexingJobInput,
): Promise<number> {
  const {
    conversationId,
    collectionName,
    filePaths,
    storageNamespace = null,
    metadata = {},
    maxAttempts = 3,
  } = input

  if (filePaths.length === 0) {
    throw new Error('enqueueIndexingJob: filePaths must not be empty')
  }

  const result = await query<{ id: string }>(
    `INSERT INTO indexing_jobs (
       conversation_id, collection_name, file_paths,
       storage_namespace, metadata, max_attempts, status
     ) VALUES ($1, $2, $3::jsonb, $4, $5::jsonb, $6, 'queued')
     RETURNING id`,
    [
      conversationId,
      collectionName,
      JSON.stringify(filePaths),
      storageNamespace,
      JSON.stringify(metadata),
      maxAttempts,
    ],
  )
  return Number(result.rows[0].id)
}

/**
 * Fetch an event by id, marking it processed atomically. Returns null
 * when another backend instance already claimed it — this is the
 * mechanism that prevents duplicate welcome-message inserts when
 * multiple backend replicas LISTEN on 'indexing_events'.
 */
export async function claimIndexingEvent(
  eventId: number,
): Promise<{
  id: number
  conversation_id: string
  job_id: number | null
  event_type: string
  payload: Record<string, unknown>
} | null> {
  const result = await query(
    `UPDATE indexing_events
        SET processed_at = NOW()
      WHERE id = $1 AND processed_at IS NULL
      RETURNING id, conversation_id, job_id, event_type, payload`,
    [eventId],
  )
  if (result.rows.length === 0) return null
  const row = result.rows[0]
  return {
    id: Number(row.id),
    conversation_id: row.conversation_id,
    job_id: row.job_id == null ? null : Number(row.job_id),
    event_type: row.event_type,
    payload: row.payload ?? {},
  }
}

/**
 * Replay events after a given id for a conversation. Used by browser
 * reconnects that need to catch up on progress emitted while they were
 * disconnected. ``sinceId`` of 0 returns all events ever persisted.
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
