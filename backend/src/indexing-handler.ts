/**
 * Stateless handler for indexing events emitted by the chatrag-worker.
 *
 * In ``WORKER_MODE=cloud_run``, workers run on a separate Cloud Run service
 * and can't write messages/conversation state directly (that logic lives
 * in TypeScript). They instead INSERT events into ``indexing_events``.
 * Any backend instance LISTEN'ing on that channel picks up NOTIFYs and
 * calls into this handler.
 *
 * Key invariants:
 *   • The caller (indexing-events-listener.ts) has *already* claimed the
 *     event row via ``claimIndexingEvent`` — this is the cross-replica
 *     single-writer guarantee. So no further dedup is needed here.
 *   • State that used to live in the upload.ts closure (``welcomeMessageId``,
 *     ``latestParsed``, ``latestTotal``) is looked up from the DB on every
 *     call instead.
 *   • Per-job metadata (``uploadedFileNames``, ``storedToOriginal``) is
 *     embedded in each event payload by the worker so we never need to
 *     join against another table.
 *   • ``emitConversationEvent`` fans out to whichever SSE clients are
 *     currently subscribed on *this* backend instance. The upstream
 *     issue of "which instance holds the browser socket" is solved by
 *     NOTIFY: all instances receive it, the one with the browser relays.
 */

import * as Sentry from '@sentry/node'
import { emitConversationEvent } from './events.js'
import {
  getMessageById,
  insertConversationMessage,
  updateConversationMessageContent,
  updateConversationStatus,
  updateFileMetadata,
} from './repositories/conversations.js'
import { query } from './db.js'

export type IndexingEventRecord = {
  id: number
  conversation_id: string
  event_type: string
  payload: Record<string, unknown>
}

type JobContext = {
  uploadedFileNames: string[]
  storedToOriginal: Record<string, string>
}

/**
 * Pull per-job metadata out of the event payload. The worker embeds this
 * in every welcome/complete event under ``_meta`` so the handler doesn't
 * have to join against any jobs table.
 */
function getJobContext(payload: Record<string, unknown>): JobContext {
  const meta = (payload._meta as Record<string, unknown> | undefined) ?? {}
  const uploadedFileNames = Array.isArray(meta.uploadedFileNames)
    ? (meta.uploadedFileNames as string[])
    : []
  const storedToOriginal =
    meta.storedToOriginal && typeof meta.storedToOriginal === 'object'
      ? (meta.storedToOriginal as Record<string, string>)
      : {}
  return { uploadedFileNames, storedToOriginal }
}

/**
 * Dispatch one claimed event. Must be idempotent with respect to
 * out-of-order delivery within reason: the worker emits events roughly
 * in order, but NOTIFY does not guarantee listener-side ordering if the
 * backend is under load.
 */
export async function handleIndexingEvent(
  event: IndexingEventRecord,
): Promise<void> {
  const { conversation_id: conversationId, event_type: eventType, payload } = event

  switch (eventType) {
    case 'page_progress': {
      // High-frequency; pure SSE relay, no DB write.
      emitConversationEvent(conversationId, {
        event: 'page_progress',
        data: {
          parsed: payload.parsed,
          total: payload.total,
        },
      })
      return
    }

    case 'welcome_message': {
      const ctx = getJobContext(payload)
      await handleWelcomeMessage(conversationId, payload, ctx)
      return
    }

    case 'wiki_message': {
      // Internal "idea file" — persist as a hidden message; never re-emitted
      // over SSE because it must not surface in any user-visible UI.
      // After a successful persist, send a lightweight `wiki_ready` event so
      // the browser can reveal the "Wiki 🗺️" button without polling.
      const wikiContent = (payload.wiki_message as string) || ''
      if (!wikiContent) return
      try {
        await insertConversationMessage({
          conversationId,
          role: 'assistant',
          content: wikiContent,
          isInternal: true,
          internalKind: (payload.internal_kind as string) || 'wiki',
        })
        emitConversationEvent(conversationId, {
          event: 'wiki_ready',
          data: {},
        })
      } catch (err: any) {
        console.error('[wiki message persist error]:', err.message)
      }
      return
    }

    case 'complete': {
      const ctx = getJobContext(payload)
      await handleComplete(conversationId, payload, ctx)
      return
    }

    case 'error': {
      const message = (payload.error as string) || 'Indexing failed'
      await updateConversationStatus(conversationId, 'failed', message)
      emitConversationEvent(conversationId, {
        event: 'error',
        data: { message },
      })
      return
    }

    default: {
      // Unknown event — log but don't throw; forward to SSE in case the
      // frontend knows what to do with it.
      emitConversationEvent(conversationId, {
        event: eventType,
        data: payload,
      })
    }
  }
}

async function handleWelcomeMessage(
  conversationId: string,
  payload: Record<string, unknown>,
  ctx: JobContext,
): Promise<void> {
  const welcomeMessage = (payload.welcome_message as string) || ''
  const fileMetadata = (payload.file_metadata as Record<string, any>) || {}
  const uploadedFileNames = ctx.uploadedFileNames
  const storedToOriginal = ctx.storedToOriginal
  const suggestedQuestions = (payload.suggested_questions as string[]) || []

  const existingWelcome = await findExistingWelcomeMessageId(conversationId)
  let welcomeMessageId = existingWelcome
  if (!welcomeMessageId) {
    const fallbackMessage =
      welcomeMessage ||
      buildFallbackWelcome(uploadedFileNames)
    welcomeMessageId = await insertConversationMessage({
      conversationId,
      role: 'assistant',
      content: fallbackMessage,
      citations: { _uploadedFileNames: uploadedFileNames },
    })
  }

  for (const [fileName, metadata] of Object.entries(fileMetadata)) {
    try {
      const origName = storedToOriginal[fileName] || fileName
      await updateFileMetadata(conversationId, origName, metadata)
    } catch (err: any) {
      console.error(`[metadata update error for ${fileName}]:`, err.message)
    }
  }

  emitConversationEvent(conversationId, {
    event: 'welcome_message',
    data: {
      messageId: welcomeMessageId,
      suggestedQuestions,
    },
  })
}

async function handleComplete(
  conversationId: string,
  payload: Record<string, unknown>,
  ctx: JobContext,
): Promise<void> {
  const suggestedQuestions = (payload.suggested_questions as string[]) || []
  const finalWelcomeMessage = (payload.welcome_message as string) || ''
  const uploadedFileNames = ctx.uploadedFileNames
  const fileMetadata = (payload.file_metadata as Record<string, any>) || {}
  const storedToOriginal = ctx.storedToOriginal
  // Read the last page_progress payload we persisted to indexing_events so
  // the welcome-UPDATE footer can say "after OCR-ing N/M pages". This
  // replaces the latestParsed/latestTotal closure vars from the old
  // in-request stream handler.
  const { parsedPages, totalPages } = await readLatestPageProgress(conversationId)

  Sentry.logger.info(
    Sentry.logger.fmt`Indexing completed for conversation ${conversationId}`,
    {
      conversation_id: conversationId,
      suggested_questions_count: suggestedQuestions.length,
      has_welcome_message: !!finalWelcomeMessage,
    },
  )

  let welcomeMessageId = await findExistingWelcomeMessageId(conversationId)

  if (!welcomeMessageId) {
    // No prior welcome emitted (e.g. fast text PDF skipped the OCR prefetch).
    const fallbackMessage =
      finalWelcomeMessage || buildFallbackWelcome(uploadedFileNames)
    welcomeMessageId = await insertConversationMessage({
      conversationId,
      role: 'assistant',
      content: fallbackMessage,
      citations: { _uploadedFileNames: uploadedFileNames },
    })
    for (const [fileName, metadata] of Object.entries(fileMetadata)) {
      try {
        const origName = storedToOriginal[fileName] || fileName
        await updateFileMetadata(conversationId, origName, metadata)
      } catch (err: any) {
        console.error(`[metadata update error for ${fileName}]:`, err.message)
      }
    }
  } else if (finalWelcomeMessage) {
    // A richer synthesized welcome arrived after the initial prefetch
    // version — merge under an UPDATE section.
    try {
      await appendWelcomeUpdate(
        welcomeMessageId,
        finalWelcomeMessage,
        parsedPages,
        totalPages,
      )
    } catch (err: any) {
      console.error('[welcome update error]:', err.message)
    }
  }

  // Suggested questions are embedded inline as [action:...] markers in
  // welcome_message content by the Python describe step — nothing to
  // persist separately here.
  await updateConversationStatus(conversationId, 'ready')

  emitConversationEvent(conversationId, {
    event: 'complete',
    data: { suggestedQuestions },
  })
}

/**
 * Lookup the id of the first assistant message in a conversation — that's
 * the welcome message. Returns null if none exists yet. This replaces
 * the `welcomeMessageId` closure variable from the old stream handler.
 */
async function findExistingWelcomeMessageId(
  conversationId: string,
): Promise<string | null> {
  const result = await query<{ id: string }>(
    `SELECT id FROM conversation_messages
      WHERE conversation_id = $1 AND role = 'assistant'
      ORDER BY created_at ASC
      LIMIT 1`,
    [conversationId],
  )
  return result.rows.length ? result.rows[0].id : null
}

/**
 * Most recent page_progress values for a conversation, sourced from the
 * indexing_events log. Returns zeros if no progress was ever emitted
 * (e.g. fast text-layer PDFs that skip OCR entirely). Used by
 * handleComplete to render the welcome-UPDATE footer.
 */
async function readLatestPageProgress(
  conversationId: string,
): Promise<{ parsedPages: number; totalPages: number }> {
  const res = await query<{ payload: any }>(
    `SELECT payload FROM indexing_events
      WHERE conversation_id = $1 AND event_type = 'page_progress'
      ORDER BY id DESC
      LIMIT 1`,
    [conversationId],
  )
  if (!res.rows.length) return { parsedPages: 0, totalPages: 0 }
  const p = res.rows[0].payload || {}
  return {
    parsedPages: Number(p.parsed) || 0,
    totalPages: Number(p.total) || 0,
  }
}

function buildFallbackWelcome(uploadedFileNames: string[]): string {
  if (!uploadedFileNames.length) {
    return 'File uploaded and ready. Ask me anything about it.'
  }
  const article =
    uploadedFileNames.length === 1 ? 'this document' : 'these documents'
  return `## ${uploadedFileNames.join(', ')}\n\nFile uploaded and ready. Ask me anything about ${article}.`
}

/**
 * Shared with upload.ts's inline path. Kept here (not duplicated) so both
 * the inline stream handler and the LISTEN-based handler produce identical
 * welcome-UPDATE rendering.
 */
export async function appendWelcomeUpdate(
  messageId: string,
  updatedWelcome: string,
  parsedPages: number,
  totalPages: number,
): Promise<void> {
  if (!updatedWelcome.trim()) return
  const current = await getMessageById(messageId)
  if (!current) return
  const original = current.content || ''
  if (original.includes(updatedWelcome.trim())) return
  const pagesInfo =
    totalPages > 0
      ? `after OCR-ing ${parsedPages || totalPages} of ${totalPages} pages`
      : 'after full OCR'
  const merged = `${original}\n\n---\n**UPDATE** — ${pagesInfo}:\n\n${updatedWelcome.trim()}`
  await updateConversationMessageContent(messageId, merged)
}
