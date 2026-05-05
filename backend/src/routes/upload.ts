import Router from '@koa/router'
import multer from '@koa/multer'
import path from 'node:path'
import { v4 as uuidv4 } from 'uuid'
import * as Sentry from '@sentry/node'
import { generateShortId } from '../utils/id.js'
import { createStorageProvider } from '../storage/index.js'
import {
  insertConversation,
  insertUploadedFile,
  updateConversationStatus,
  insertAccessToken,
  insertConversationMessage,
  updateFileMetadata,
  resolveConversationRole,
  updateConversationMessageContent,
  getMessageById,
} from '../repositories/conversations.js'
import { config } from '../config.js'
import { indexConversationStream, describeUrl } from '../python/indexing.js'
import logger from '../logger.js'

import { emitConversationEvent } from '../events.js'
import { deriveToken } from '../security.js'
import { generateSignedUploadUrl, downloadGcsFileToLocal } from '../storage/gcs-storage.js'
import { getConversationToken, getTraceIdHeader } from '../utils/request.js'
import { MAX_FILE_SIZE } from '../constants.js'
import { publishIndexingJob } from '../indexing-jobs.js'

const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: MAX_FILE_SIZE } })
export const uploadRouter = new Router()

/**
 * When the initial OCR-prefetch welcome is later replaced by a richer,
 * full-OCR-synthesized welcome, keep the user's original message intact
 * and append the richer version below an UPDATE separator.  This matches
 * the "initial welcome + UPDATE after full OCR" UX contract.
 */
async function appendWelcomeUpdate(
  messageId: string,
  updatedWelcome: string,
  parsedPages: number,
  totalPages: number,
): Promise<void> {
  if (!updatedWelcome.trim()) return
  const current = await getMessageById(messageId)
  if (!current) return
  const original = current.content || ''
  // Guard against duplicate updates when the same synthesized text is re-emitted.
  if (original.includes(updatedWelcome.trim())) return
  const pagesInfo =
    totalPages > 0
      ? `after OCR-ing ${parsedPages || totalPages} of ${totalPages} pages`
      : 'after full OCR'
  const merged = `${original}\n\n---\n**UPDATE** — ${pagesInfo}:\n\n${updatedWelcome.trim()}`
  await updateConversationMessageContent(messageId, merged)
}

/** Typed error raised when the Python indexing pipeline returns an error event. */
class IndexingError extends Error {
  constructor(
    message: string,
    public readonly code?: string,
  ) {
    super(message)
    this.name = 'IndexingError'
  }
}

/**
 * Extract a user-facing error message from an indexing stream error event.
 * Recognises the 'sexual_content' error code and returns a clean message.
 */
function resolveIndexingError(data: Record<string, any>): IndexingError {
  const code = data.error_code as string | undefined
  const raw = (data.error as string) || 'Indexing failed'
  if (code === 'sexual_content') {
    return new IndexingError(
      'This file contains sexual or explicit content and cannot be uploaded.',
      code,
    )
  }
  return new IndexingError(raw)
}

uploadRouter.post('/upload', upload.array('files'), async (ctx) => {
  const traceId = getTraceIdHeader(ctx) || (ctx.state.traceId as string | undefined) || ''
  const sentryTrace = ctx.get('sentry-trace') || ''
  const baggage = ctx.get('baggage') || ''
  if (traceId) {
    Sentry.setTag('trace_id', traceId)
    Sentry.captureMessage(`Backend accepted /upload [${traceId}]`, 'debug')
  }

  const files = (ctx.files as multer.File[]) || []
  if (!files.length) {
    ctx.status = 400
    ctx.body = { error: 'No files uploaded' }
    return
  }

  // Optional user browser language sent by the frontend for welcome-message generation
  const userLanguage = (ctx.request.body as Record<string, string>)?.userLanguage || undefined

  const videoFiles = files.filter((f) => f.mimetype?.startsWith('video/'))
  if (videoFiles.length) {
    ctx.status = 400
    ctx.body = { error: 'Video files are not supported.' }
    return
  }

  const conversationId = generateShortId()
  const salt = uuidv4()
  const ownerPassword = deriveToken(conversationId, salt)
  const namespace = conversationId
  const collectionName = `conversation_${conversationId}`
  const storage = createStorageProvider()

  await insertConversation({
    id: conversationId,
    salt: salt,
    display_name: null,
    status: 'processing',
    storage_namespace: namespace,
    vector_collection_name: collectionName,
    indexing_mode: 'script',
    error_message: null,
    parent_message_id: null,
    parent_conversation_id: null,
  })

  // Create owner access token - use derived token
  await insertAccessToken({
    token: ownerPassword,
    conversation_id: conversationId,
    role: 'owner',
  })

  const absolutePaths: string[] = []
  const jobFilePaths: string[] = []
  const uploadedFileNames: string[] = []
  const storedToOriginal: Record<string, string> = {}

  for (const file of files) {
    const originalName = Buffer.from(file.originalname, 'latin1').toString('utf8').normalize('NFC')
    const saved = await storage.save(namespace, originalName, {
      originalName,
      mimeType: file.mimetype || 'application/octet-stream',
      buffer: file.buffer,
    })

    const storedName = path.basename(saved.storageKey)

    await insertUploadedFile({
      id: uuidv4(),
      conversation_id: conversationId,
      original_name: originalName,
      stored_name: storedName,
      mime_type: file.mimetype || 'application/octet-stream',
      size_bytes: file.size,
      storage_key: saved.storageKey,
    })

    uploadedFileNames.push(originalName)
    storedToOriginal[storedName] = originalName
    if (saved.absolutePath) {
      absolutePaths.push(saved.absolutePath)
    }
    // In cloud_run worker mode the indexer usually runs on a separate
    // instance with its own ephemeral FS. Send the local path AND a
    // gs:// URI (pipe-separated) so the worker uses the local file when
    // it happens to be on the same instance (e.g. shared volume / warm
    // reuse) and falls back to downloading from GCS otherwise.
    if (config.workerMode === 'cloud_run' && config.storageProvider === 'gcs') {
      const gsUri = `gs://${config.gcsBucket}/${saved.storageKey}`
      jobFilePaths.push(saved.absolutePath ? `${saved.absolutePath}|${gsUri}` : gsUri)
    } else if (saved.absolutePath) {
      jobFilePaths.push(saved.absolutePath)
    }
  }

  // Fire-and-forget: stream indexing events and emit SSE updates.
  // In 'cloud_run' worker mode, publish to GCP Pub/Sub; chatrag-worker
  // pulls the job and emits progress to indexing_events, which the SSE
  // listener relays to the browser. In 'inline' mode (dev / single-node),
  // run indexing in-process and stream events directly.
  if (config.workerMode === 'cloud_run') {
    publishIndexingJob({
      conversationId,
      collectionName,
      filePaths: jobFilePaths,
      storageNamespace: namespace,
      metadata: {
        uploadedFileNames,
        storedToOriginal,
        traceId,
        sentryTrace,
        baggage,
        userLanguage: userLanguage ?? null,
      },
    }).catch(async (err: Error) => {
      logger.error({ conversationId, err: err.message }, 'publishIndexingJob failed')
      await updateConversationStatus(conversationId, 'failed', err.message)
      emitConversationEvent(conversationId, {
        event: 'error',
        data: { message: err.message },
      })
    })
  } else {
    ;(async () => {
      let welcomeMessageId: string | undefined
      let latestParsed = 0
      let latestTotal = 0
      try {
        const stream = indexConversationStream({
          conversationId,
          collectionName,
          files: absolutePaths,
          traceId,
          userLanguage,
        })

        for await (const { event, data } of stream) {
          if (event === 'welcome_message') {
            const welcomeMessage = (data.welcome_message as string) || ''
            const fileMetadata = (data.file_metadata as Record<string, any>) || {}
            const earlySuggestedQuestions = (data.suggested_questions as string[]) || []
            const fallbackMessage =
              welcomeMessage ||
              `## ${uploadedFileNames.join(', ')}\n\nFile uploaded and ready. Ask me anything about ${uploadedFileNames.length === 1 ? 'this document' : 'these documents'}.`
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
            emitConversationEvent(conversationId, {
              event: 'welcome_message',
              data: {
                messageId: welcomeMessageId,
                suggestedQuestions: earlySuggestedQuestions,
              },
            })
          } else if (event === 'wiki_message') {
            // Hidden "idea file" — stored as an internal message and
            // injected into ANSWER_PROMPT on every subsequent /ask. Never
            // surfaced to the user, so no SSE re-broadcast.
            const wikiContent = (data.wiki_message as string) || ''
            if (wikiContent) {
              try {
                await insertConversationMessage({
                  conversationId,
                  role: 'assistant',
                  content: wikiContent,
                  isInternal: true,
                  internalKind: (data.internal_kind as string) || 'wiki',
                })
                // Notify the browser that the wiki is ready — frontend shows
                // the "Wiki 🗺️" button in the first-message action bar.
                emitConversationEvent(conversationId, {
                  event: 'wiki_ready',
                  data: {},
                })
              } catch (err: any) {
                console.error('[wiki message persist error]:', err.message)
              }
            }
          } else if (event === 'complete') {
            Sentry.logger.info(
              Sentry.logger.fmt`Indexing completed for conversation ${conversationId}`,
              {
                conversation_id: conversationId,
                file_count: files.length,
                suggested_questions_count: ((data.suggested_questions as string[]) || []).length,
                has_welcome_message: !!data.welcome_message,
              },
            )
            const suggestedQuestions = (data.suggested_questions as string[]) || []
            const finalWelcomeMessage = (data.welcome_message as string) || ''
            // If welcome message was not emitted earlier (no on_progress callback hit),
            // insert it now as a fallback
            if (!welcomeMessageId) {
              const fileMetadata = (data.file_metadata as Record<string, any>) || {}
              const fallbackMessage =
                finalWelcomeMessage ||
                `## ${uploadedFileNames.join(', ')}\n\nFile uploaded and ready. Ask me anything about ${uploadedFileNames.length === 1 ? 'this document' : 'these documents'}.`
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
              // A richer synthesized welcome message arrived after the initial
              // OCR-prefetch version — merge it into the original under an UPDATE
              // section so the user sees both the warm first-impression and the
              // full-document synthesis.
              try {
                await appendWelcomeUpdate(
                  welcomeMessageId,
                  finalWelcomeMessage,
                  latestParsed,
                  latestTotal,
                )
              } catch (err: any) {
                console.error('[welcome update error]:', err.message)
              }
            }
            await updateConversationStatus(conversationId, 'ready')
            emitConversationEvent(conversationId, {
              event: 'complete',
              data: { suggestedQuestions },
            })
          } else if (event === 'page_progress') {
            latestParsed = Number(data.parsed) || latestParsed
            latestTotal = Number(data.total) || latestTotal
            emitConversationEvent(conversationId, {
              event: 'page_progress',
              data: { parsed: data.parsed, total: data.total },
            })
          } else if (event === 'error') {
            throw resolveIndexingError(data)
          }
        }
      } catch (error: any) {
        await updateConversationStatus(conversationId, 'failed', error.message)
        emitConversationEvent(conversationId, {
          event: 'error',
          data: { message: error.message },
        })
      }
    })()
  }

  ctx.body = {
    conversationId,
    status: 'processing',
    url: `/c/${conversationId}`,
    ownerPassword,
  }
})

// ── Direct-to-GCS upload for large files (bypasses Cloud Run 32 MiB proxy limit) ──

uploadRouter.post('/upload/signed-url', async (ctx) => {
  if (config.storageProvider !== 'gcs') {
    ctx.status = 400
    ctx.body = { error: 'Direct upload only available with GCS storage' }
    return
  }

  const { files } = ctx.request.body as {
    files?: Array<{ name: string; mimeType: string; size: number }>
  }
  if (!files?.length) {
    ctx.status = 400
    ctx.body = { error: 'No files specified' }
    return
  }

  if (files.length > 20) {
    ctx.status = 400
    ctx.body = { error: 'Maximum 20 files per upload' }
    return
  }

  const videoFiles = files.filter((f) => f.mimeType?.startsWith('video/'))
  if (videoFiles.length) {
    ctx.status = 400
    ctx.body = { error: 'Video files are not supported.' }
    return
  }

  const conversationId = generateShortId()
  const salt = uuidv4()
  const ownerPassword = deriveToken(conversationId, salt)
  const namespace = conversationId
  const collectionName = `conversation_${conversationId}`

  await insertConversation({
    id: conversationId,
    salt,
    display_name: null,
    status: 'uploading',
    storage_namespace: namespace,
    vector_collection_name: collectionName,
    indexing_mode: 'script',
    error_message: null,
    parent_message_id: null,
    parent_conversation_id: null,
  })

  await insertAccessToken({
    token: ownerPassword,
    conversation_id: conversationId,
    role: 'owner',
  })

  const signedUrls: Array<{ name: string; signedUrl: string; gcsKey: string; storedName: string }> =
    []

  for (const file of files) {
    const originalName = file.name.normalize('NFC')
    const mimeType = file.mimeType || 'application/octet-stream'
    const { gcsKey, storedName, signedUrl } = await generateSignedUploadUrl(
      namespace,
      originalName,
      mimeType,
    )
    signedUrls.push({ name: originalName, signedUrl, gcsKey, storedName })
  }

  ctx.body = {
    conversationId,
    ownerPassword,
    url: `/c/${conversationId}`,
    signedUrls,
  }
})

uploadRouter.post('/upload/finalize', async (ctx) => {
  const traceId = getTraceIdHeader(ctx) || (ctx.state.traceId as string | undefined) || ''
  const sentryTrace = ctx.get('sentry-trace') || ''
  const baggage = ctx.get('baggage') || ''

  const { conversationId, files: fileEntries, userLanguage } = ctx.request.body as {
    conversationId?: string
    userLanguage?: string
    files?: Array<{
      name: string
      mimeType: string
      size: number
      gcsKey: string
      storedName: string
    }>
  }

  if (!conversationId || !fileEntries?.length) {
    ctx.status = 400
    ctx.body = { error: 'Missing conversationId or files' }
    return
  }

  const token = getConversationToken(ctx)
  if (!token) {
    ctx.status = 401
    ctx.body = { error: 'Missing auth token' }
    return
  }

  const role = await resolveConversationRole(conversationId, token)
  if (role !== 'owner') {
    ctx.status = 403
    ctx.body = { error: 'Only the owner can finalize uploads' }
    return
  }

  await updateConversationStatus(conversationId, 'processing')

  const absolutePaths: string[] = []
  const jobFilePaths: string[] = []
  const uploadedFileNames: string[] = []
  const storedToOriginal: Record<string, string> = {}
  const namespace = conversationId

  for (const entry of fileEntries) {
    const originalName = entry.name.normalize('NFC')
    const storedName = entry.storedName

    // Validate gcsKey belongs to this conversation's namespace (prevent path traversal)
    const expectedPrefix = `${namespace}/`
    if (!entry.gcsKey.startsWith(expectedPrefix) || entry.gcsKey.includes('..')) {
      ctx.status = 400
      ctx.body = { error: 'Invalid file reference' }
      return
    }

    // Download from GCS to local disk for Python indexing
    const absolutePath = await downloadGcsFileToLocal(entry.gcsKey, namespace)

    await insertUploadedFile({
      id: uuidv4(),
      conversation_id: conversationId,
      original_name: originalName,
      stored_name: storedName,
      mime_type: entry.mimeType || 'application/octet-stream',
      size_bytes: entry.size,
      storage_key: entry.gcsKey,
    })

    uploadedFileNames.push(originalName)
    storedToOriginal[storedName] = originalName
    absolutePaths.push(absolutePath)
    if (config.workerMode === 'cloud_run') {
      // Prefer local (cached on this instance after downloadGcsFileToLocal)
      // and fall back to gs:// for workers on other instances.
      jobFilePaths.push(`${absolutePath}|gs://${config.gcsBucket}/${entry.gcsKey}`)
    } else {
      jobFilePaths.push(absolutePath)
    }
  }

  const collectionName = `conversation_${conversationId}`

  // Fire-and-forget: stream indexing events and emit SSE updates. See the
  // /upload route above for the full branch rationale.
  if (config.workerMode === 'cloud_run') {
    publishIndexingJob({
      conversationId: conversationId as string,
      collectionName,
      filePaths: jobFilePaths,
      storageNamespace: conversationId as string,
      metadata: {
        uploadedFileNames,
        storedToOriginal,
        traceId,
        sentryTrace,
        baggage,
        userLanguage: userLanguage ?? null,
      },
    }).catch(async (err: Error) => {
      logger.error({ conversationId, err: err.message }, 'publishIndexingJob failed')
      await updateConversationStatus(conversationId as string, 'failed', err.message)
      emitConversationEvent(conversationId as string, {
        event: 'error',
        data: { message: err.message },
      })
    })
  } else {
    ;(async () => {
      let welcomeMessageId: string | undefined
      let latestParsed = 0
      let latestTotal = 0
      try {
        const stream = indexConversationStream({
          conversationId: conversationId as string,
          collectionName,
          files: absolutePaths,
          traceId,
          userLanguage,
        })

        for await (const { event, data } of stream) {
          if (event === 'welcome_message') {
            const welcomeMessage = (data.welcome_message as string) || ''
            const fileMetadata = (data.file_metadata as Record<string, any>) || {}
            const earlySuggestedQuestions = (data.suggested_questions as string[]) || []
            const fallbackMessage =
              welcomeMessage ||
              `## ${uploadedFileNames.join(', ')}\n\nFile uploaded and ready. Ask me anything about ${uploadedFileNames.length === 1 ? 'this document' : 'these documents'}.`
            welcomeMessageId = await insertConversationMessage({
              conversationId: conversationId as string,
              role: 'assistant',
              content: fallbackMessage,
              citations: { _uploadedFileNames: uploadedFileNames },
            })
            for (const [fileName, metadata] of Object.entries(fileMetadata)) {
              try {
                const origName = storedToOriginal[fileName] || fileName
                await updateFileMetadata(conversationId as string, origName, metadata)
              } catch (err: any) {
                console.error(`[metadata update error for ${fileName}]:`, err.message)
              }
            }
            emitConversationEvent(conversationId, {
              event: 'welcome_message',
              data: {
                messageId: welcomeMessageId,
                suggestedQuestions: earlySuggestedQuestions,
              },
            })
          } else if (event === 'wiki_message') {
            const wikiContent = (data.wiki_message as string) || ''
            if (wikiContent) {
              try {
                await insertConversationMessage({
                  conversationId: conversationId as string,
                  role: 'assistant',
                  content: wikiContent,
                  isInternal: true,
                  internalKind: (data.internal_kind as string) || 'wiki',
                })
                emitConversationEvent(conversationId as string, {
                  event: 'wiki_ready',
                  data: {},
                })
              } catch (err: any) {
                console.error('[wiki message persist error]:', err.message)
              }
            }
          } else if (event === 'c4_message') {
            const c4Content = (data.c4_message as string) || ''
            if (c4Content) {
              try {
                await insertConversationMessage({
                  conversationId: conversationId as string,
                  role: 'assistant',
                  content: c4Content,
                  isInternal: true,
                  internalKind: 'c4',
                })
                emitConversationEvent(conversationId as string, {
                  event: 'c4_ready',
                  data: {},
                })
              } catch (err: any) {
                console.error('[c4 message persist error]:', err.message)
              }
            }
          } else if (event === 'complete') {
            const suggestedQuestions = (data.suggested_questions as string[]) || []
            const finalWelcomeMessage = (data.welcome_message as string) || ''
            if (!welcomeMessageId) {
              const fileMetadata = (data.file_metadata as Record<string, any>) || {}
              const fallbackMessage =
                finalWelcomeMessage ||
                `## ${uploadedFileNames.join(', ')}\n\nFile uploaded and ready. Ask me anything about ${uploadedFileNames.length === 1 ? 'this document' : 'these documents'}.`
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
              try {
                await appendWelcomeUpdate(
                  welcomeMessageId,
                  finalWelcomeMessage,
                  latestParsed,
                  latestTotal,
                )
              } catch (err: any) {
                console.error('[welcome update error]:', err.message)
              }
            }
            await updateConversationStatus(conversationId, 'ready')
            emitConversationEvent(conversationId, {
              event: 'complete',
              data: { suggestedQuestions },
            })
          } else if (event === 'page_progress') {
            latestParsed = Number(data.parsed) || latestParsed
            latestTotal = Number(data.total) || latestTotal
            emitConversationEvent(conversationId, {
              event: 'page_progress',
              data: { parsed: data.parsed, total: data.total },
            })
          } else if (event === 'error') {
            throw resolveIndexingError(data)
          }
        }
      } catch (error: any) {
        await updateConversationStatus(conversationId, 'failed', error.message)
        emitConversationEvent(conversationId, {
          event: 'error',
          data: { message: error.message },
        })
      }
    })()
  }

  ctx.body = {
    conversationId,
    status: 'processing',
    url: `/c/${conversationId}`,
  }
})

uploadRouter.post('/upload-url', async (ctx) => {
  const traceId = getTraceIdHeader(ctx) || (ctx.state.traceId as string | undefined) || ''

  const { url } = ctx.request.body as { url?: string }
  if (!url || typeof url !== 'string') {
    ctx.status = 400
    ctx.body = { error: 'No URL provided' }
    return
  }

  // Basic URL validation
  let parsed: URL
  try {
    parsed = new URL(url)
    if (!['http:', 'https:'].includes(parsed.protocol)) {
      throw new Error('Invalid protocol')
    }
  } catch {
    ctx.status = 400
    ctx.body = { error: 'Invalid URL' }
    return
  }

  const conversationId = generateShortId()
  const salt = uuidv4()
  const ownerPassword = deriveToken(conversationId, salt)
  const namespace = conversationId
  const collectionName = `conversation_${conversationId}`

  await insertConversation({
    id: conversationId,
    salt: salt,
    display_name: null,
    status: 'processing',
    storage_namespace: namespace,
    vector_collection_name: collectionName,
    indexing_mode: 'script',
    error_message: null,
    parent_message_id: null,
    parent_conversation_id: null,
  })

  await insertAccessToken({
    token: ownerPassword,
    conversation_id: conversationId,
    role: 'owner',
  })

  describeUrl({
    url,
    conversationId,
    collectionName,
    traceId,
  })
    .then(async (result) => {
      const welcomeMessage = result.parsedJson?.welcome_message || ''
      const suggestedQuestions: string[] = result.parsedJson?.suggested_questions || []
      const fallbackMessage =
        welcomeMessage ||
        `## ${parsed.hostname}\n\nWebsite loaded and ready. Ask me anything about this page.`
      const messageId = await insertConversationMessage({
        conversationId,
        role: 'assistant',
        content: fallbackMessage,
        citations: { _sourceUrl: url },
      })
      await updateConversationStatus(conversationId, 'ready')
      emitConversationEvent(conversationId, {
        event: 'welcome_message',
        data: { messageId, suggestedQuestions },
      })
      emitConversationEvent(conversationId, {
        event: 'complete',
        data: { suggestedQuestions },
      })
    })
    .catch(async (error) => {
      await updateConversationStatus(conversationId, 'failed', error.message)
      emitConversationEvent(conversationId, {
        event: 'error',
        data: { message: error.message },
      })
      emitConversationEvent(conversationId, {
        event: 'complete',
        data: { status: 'failed' },
      })
    })

  ctx.body = {
    conversationId,
    status: 'processing',
    url: `/c/${conversationId}`,
    ownerPassword,
  }
})
