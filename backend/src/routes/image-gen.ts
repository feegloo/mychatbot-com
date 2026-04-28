import Router from '@koa/router'
import path from 'node:path'
import fs from 'node:fs/promises'
import { z } from 'zod'
import {
  getConversation,
  insertConversationMessage,
  resolveConversationRole,
} from '../repositories/conversations.js'
import { announceImage, generateImage, generateImageStream } from '../python/image-gen.js'
import { registerReusableImage } from '../python/reusable-image.js'
import { insertGeneratedImage } from '../repositories/generated-images.js'
import { buildChatHistory, getWelcomeMessages } from '../utils/chat-history.js'
import { config } from '../config.js'
import { getConversationToken } from '../utils/request.js'
import { SHORT_ID_RE } from '../constants.js'
import { uploadLocalFileToGcs, downloadFromGcs } from '../storage/gcs-storage.js'
import { resolveReferenceImagePaths } from '../utils/reference-images.js'
import logger from '../logger.js'
import { bindStreamLifecycle, isStreamClosed } from '../utils/stream-lifecycle.js'
import { resolveConversationLanguage } from '../utils/conversation-language.js'

// File names are resolved against the conversation's storage dir server-side.
// We reject anything that could escape the storage dir (slashes, `..`) to
// prevent path traversal into unrelated files on disk.
const SAFE_FILE_NAME_RE = /^[^/\\]+$/

const imageGenSchema = z.object({
  conversationId: z.string().regex(SHORT_ID_RE),
  question: z.string().min(1),
  userId: z.number().int().min(0).optional(),
  language: z.string().trim().min(2).max(16).optional(),
  referenceImageFileNames: z
    .array(z.string().regex(SAFE_FILE_NAME_RE).refine((n) => !n.includes('..'), 'invalid file name'))
    .max(4)
    .optional(),
})

export const imageGenRouter = new Router()

type ImageGenResult = {
  file_name: string
  image_prompt: string
  image_title: string
  rag_sources?: Array<{
    chunk_id: string
    text: string
    file_name: string
    section?: string | null
    page?: number | null
  }>
}

const imageStreamTelemetry = {
  totalStreams: 0,
  streamsWithRealPartial: 0,
  streamsWithSyntheticPartial: 0,
  totalForwardedPartials: 0,
}

/**
 * Shared post-generation pipeline: GCS upload + DB row + reusable-image
 * index. Returns the response body used by both the blocking POST
 * /generate-image route and the NDJSON streaming variant.
 */
async function finalizeGeneratedImage(params: {
  conversationId: string
  question: string
  userMessageId: string
  result: ImageGenResult
  conversation: { storage_namespace: string }
  files: Array<{ original_name: string; size_bytes: string | number }>
  storageDir: string
}): Promise<{
  answer: string
  citations: Array<{
    fileName: string
    chunkId: string
    text: string
    section: string | null
    page: number | null
  }>
  assistantMessageId: string
  generatedImage: {
    fileName: string
    imagePrompt: string
    imageTitle: string
  }
}> {
  const {
    conversationId,
    question,
    result,
    conversation,
    files,
    storageDir,
  } = params

  if (config.storageProvider === 'gcs' && config.gcsBucket) {
    try {
      const localPath = path.join(storageDir, result.file_name)
      const gcsKey = `${conversation.storage_namespace}/${result.file_name}`
      await uploadLocalFileToGcs(localPath, gcsKey, 'image/png')
    } catch (err) {
      logger.error({ err, fileName: result.file_name }, 'failed to upload generated image to GCS')
    }
  }

  const imageUrl = `/api/storage/${conversationId}/${result.file_name}`
  const title = result.image_title || 'Generated Image'
  const citations = (result.rag_sources || []).map((s) => ({
    fileName: s.file_name,
    chunkId: s.chunk_id,
    text: s.text,
    section: s.section ?? null,
    page: s.page ?? null,
  }))
  const sourceMarkers = citations.length
    ? ' ' + citations.map((_, i) => `[${i + 1}]`).join('')
    : ''
  // Append a "Generate next variant" action so the user can immediately
  // produce a follow-up image using the just-generated file as a reference.
  // The |ref: suffix encodes the file name; the frontend strips it from the
  // visible label and passes it as referenceImageFileNames to the backend.
  const variantAction = `[action:Generate next variant 🎨|ref:${result.file_name}]`
  const answer =
    `![${title}](${imageUrl})\n\n<p class="image-caption">"${title}"${sourceMarkers}</p>\n\n` +
    variantAction

  const assistantMsgId = await insertConversationMessage({
    conversationId,
    role: 'assistant',
    content: answer,
    citations: {
      _generatedImageDescription: result.image_prompt,
      _imageSources: citations,
    },
  })

  try {
    const sourceOriginalNames = files.map((f) => f.original_name)
    const imageId = await insertGeneratedImage({
      conversationId,
      messageId: assistantMsgId,
      storageNamespace: conversation.storage_namespace,
      fileName: result.file_name,
      imageTitle: result.image_title || title,
      imagePrompt: result.image_prompt || null,
      userPrompt: question,
      sourceOriginalNames,
      sourceSizeBytes: files.map((f) => Number(f.size_bytes)),
    })
    await registerReusableImage({
      imageId,
      conversationId,
      storageNamespace: conversation.storage_namespace,
      fileName: result.file_name,
      imageTitle: result.image_title || title,
      imagePrompt: result.image_prompt,
      userPrompt: question,
      sourceOriginalNames,
    })
  } catch (err) {
    logger.warn({ err, conversationId, assistantMsgId }, 'failed to register generated image')
  }

  return {
    answer,
    citations,
    assistantMessageId: assistantMsgId,
    generatedImage: {
      fileName: result.file_name,
      imagePrompt: result.image_prompt,
      imageTitle: result.image_title,
    },
  }
}

imageGenRouter.post('/generate-image', async (ctx) => {
  const parsed = imageGenSchema.safeParse(ctx.request.body)
  if (!parsed.success) {
    ctx.status = 400
    ctx.body = { error: 'Invalid request' }
    return
  }

  const { conversationId, question, userId, language, referenceImageFileNames } = parsed.data
  const conversationLanguage = resolveConversationLanguage(language)

  const token = getConversationToken(ctx)
  const role = await resolveConversationRole(conversationId, token)
  if (role !== 'owner' && role !== 'editor') {
    ctx.status = 403
    ctx.body = { error: 'Only the conversation owner can generate images' }
    return
  }

  const data = await getConversation(conversationId)
  if (!data.conversation) {
    ctx.status = 404
    ctx.body = { error: 'Conversation not found' }
    return
  }

  // Insert user message (the image generation request)
  const userMsgId = await insertConversationMessage({
    conversationId,
    role: 'user',
    content: question,
    userId: userId || 0,
  })

  const welcomeMessages = data.parentWelcomeContents.length
    ? data.parentWelcomeContents
    : getWelcomeMessages(data.messages)

  const chatHistory = buildChatHistory(data.messages)

  const storageDir = path.join(config.storageRoot, data.conversation.storage_namespace)

  // If the caller did not explicitly pick reference files, auto-attach the
  // conversation's uploaded images. This keeps visual context for action
  // buttons like "Generate an image inspired by: Screenshot 🎨" where the
  // original uploaded image is the intended subject. On Cloud Run the
  // file may live only in GCS on a different instance, so hydrate it.
  const canHydrateFromGcs = config.storageProvider === 'gcs' && Boolean(config.gcsBucket)
  const referenceImagePaths = await resolveReferenceImagePaths({
    explicitFileNames: referenceImageFileNames,
    files: data.files,
    storageDir,
    storageRoot: config.storageRoot,
    hydrateFromGcs: canHydrateFromGcs
      ? (storageKey, localPath) => downloadFromGcs(storageKey, localPath).then(() => undefined)
      : undefined,
    onHydrateError: (storageKey, err) =>
      logger.warn({ err, storageKey }, 'failed to hydrate reference image from GCS'),
  })

  const result = await generateImage({
    question,
    storageDir,
    welcomeMessages,
    collectionName: data.conversation.vector_collection_name,
    conversationId,
    chatHistory: chatHistory.slice(-6),
    quality: 'low',
    referenceImagePaths,
    conversationLanguageCode: conversationLanguage.code || undefined,
    conversationLanguageName: conversationLanguage.nativeName || undefined,
  })

  const finalized = await finalizeGeneratedImage({
    conversationId,
    question,
    userMessageId: userMsgId,
    result,
    conversation: data.conversation,
    files: data.files,
    storageDir,
  })

  ctx.body = {
    answer: finalized.answer,
    citations: finalized.citations,
    userMessageId: userMsgId,
    assistantMessageId: finalized.assistantMessageId,
    generatedImage: finalized.generatedImage,
  }
})

const announceImageSchema = z.object({
  conversationId: z.string().regex(SHORT_ID_RE),
  question: z.string().min(1),
  language: z.string().trim().min(2).max(16).optional(),
})

imageGenRouter.post('/announce-image', async (ctx) => {
  const parsed = announceImageSchema.safeParse(ctx.request.body)
  if (!parsed.success) {
    ctx.status = 400
    ctx.body = { error: 'Invalid request' }
    return
  }

  const { conversationId, question, language } = parsed.data
  const conversationLanguage = resolveConversationLanguage(language)

  const token = getConversationToken(ctx)
  const role = await resolveConversationRole(conversationId, token)
  if (role !== 'owner' && role !== 'editor') {
    ctx.status = 403
    ctx.body = { error: 'Only the conversation owner can generate images' }
    return
  }

  const data = await getConversation(conversationId)
  if (!data.conversation) {
    ctx.status = 404
    ctx.body = { error: 'Conversation not found' }
    return
  }

  const welcomeMessages = data.parentWelcomeContents.length
    ? data.parentWelcomeContents
    : getWelcomeMessages(data.messages)
  const chatHistory = buildChatHistory(data.messages).slice(-6)

  try {
    const { announcement } = await announceImage({
      question,
      welcomeMessages,
      chatHistory,
      conversationLanguageCode: conversationLanguage.code || undefined,
      conversationLanguageName: conversationLanguage.nativeName || undefined,
    })
    ctx.body = { announcement }
  } catch (err) {
    // The announcement is a nice-to-have — if the LLM call fails we still
    // want image generation to proceed, so return an empty announcement
    // rather than surfacing an error to the client.
    logger.warn({ err }, 'failed to build image announcement')
    ctx.body = { announcement: '' }
  }
})

imageGenRouter.post('/generate-image-stream', async (ctx) => {
  const parsed = imageGenSchema.safeParse(ctx.request.body)
  if (!parsed.success) {
    ctx.status = 400
    ctx.body = { error: 'Invalid request' }
    return
  }

  const { conversationId, question, userId, language, referenceImageFileNames } = parsed.data
  const conversationLanguage = resolveConversationLanguage(language)

  const token = getConversationToken(ctx)
  const role = await resolveConversationRole(conversationId, token)
  if (role !== 'owner' && role !== 'editor') {
    ctx.status = 403
    ctx.body = { error: 'Only the conversation owner can generate images' }
    return
  }

  const data = await getConversation(conversationId)
  if (!data.conversation) {
    ctx.status = 404
    ctx.body = { error: 'Conversation not found' }
    return
  }

  const userMsgId = await insertConversationMessage({
    conversationId,
    role: 'user',
    content: question,
    userId: userId || 0,
  })

  const welcomeMessages = data.parentWelcomeContents.length
    ? data.parentWelcomeContents
    : getWelcomeMessages(data.messages)
  const chatHistory = buildChatHistory(data.messages).slice(-6)
  const storageDir = path.join(config.storageRoot, data.conversation.storage_namespace)
  const canHydrateFromGcs = config.storageProvider === 'gcs' && Boolean(config.gcsBucket)
  const referenceImagePaths = await resolveReferenceImagePaths({
    explicitFileNames: referenceImageFileNames,
    files: data.files,
    storageDir,
    storageRoot: config.storageRoot,
    hydrateFromGcs: canHydrateFromGcs
      ? (storageKey, localPath) => downloadFromGcs(storageKey, localPath).then(() => undefined)
      : undefined,
    onHydrateError: (storageKey, err) =>
      logger.warn({ err, storageKey }, 'failed to hydrate reference image from GCS'),
  })

  // Set up SSE stream. Using the same pattern as conversations-stream so
  // proxies keep the connection alive and flush events eagerly.
  ctx.req.socket.setTimeout(0)
  ctx.req.socket.setNoDelay(true)
  ctx.req.socket.setKeepAlive(true)
  ctx.status = 200
  ctx.respond = false
  const res = ctx.res
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    Connection: 'keep-alive',
    'X-Accel-Buffering': 'no',
  })

  const upstreamAbort = new AbortController()
  const cleanup = bindStreamLifecycle(ctx.req, res, () => {
    upstreamAbort.abort()
  })

  const send = (event: string, payload: Record<string, unknown>): boolean => {
    if (isStreamClosed(res)) {
      cleanup()
      return false
    }

    try {
      res.write(`event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`)
      return true
    } catch {
      cleanup()
      return false
    }
  }

  if (!send('user_message', { userMessageId: userMsgId })) return

  imageStreamTelemetry.totalStreams += 1

  const logImageStreamTelemetry = (params: {
    partialCount: number
    syntheticPartialUsed: boolean
    status: 'completed' | 'failed'
    reason?: string
  }) => {
    if (params.partialCount > 0) {
      imageStreamTelemetry.streamsWithRealPartial += 1
      imageStreamTelemetry.totalForwardedPartials += params.partialCount
    }
    if (params.syntheticPartialUsed) {
      imageStreamTelemetry.streamsWithSyntheticPartial += 1
    }

    logger.info(
      {
        event: 'image_stream_partial_telemetry',
        status: params.status,
        reason: params.reason,
        conversationId,
        partial_count: params.partialCount,
        synthetic_partial_used: params.syntheticPartialUsed,
        counters: {
          total_streams: imageStreamTelemetry.totalStreams,
          streams_with_real_partial: imageStreamTelemetry.streamsWithRealPartial,
          streams_with_synthetic_partial: imageStreamTelemetry.streamsWithSyntheticPartial,
          total_forwarded_partials: imageStreamTelemetry.totalForwardedPartials,
        },
      },
      'image stream partial telemetry',
    )
  }

  let partialCount = 0
  let syntheticPartialUsed = false

  try {
    let finalResult: ImageGenResult | null = null
    for await (const evt of generateImageStream({
      question,
      storageDir,
      welcomeMessages,
      collectionName: data.conversation.vector_collection_name,
      conversationId,
      chatHistory,
      quality: 'low',
      referenceImagePaths,
      conversationLanguageCode: conversationLanguage.code || undefined,
      conversationLanguageName: conversationLanguage.nativeName || undefined,
      signal: upstreamAbort.signal,
    })) {
      if (evt.event === 'prompt_ready') {
        logger.info('🎬 Backend forwarding prompt_ready event')
        if (!send('prompt_ready', evt.data as unknown as Record<string, unknown>)) return
      } else if (evt.event === 'partial') {
        partialCount++
        logger.info(`🎬 Backend forwarding partial #${partialCount} (index=${(evt.data as any)?.index})`)
        if (!send('partial', evt.data as unknown as Record<string, unknown>)) {
          logger.warn('⚠️ Failed to send partial event - stream may be closed')
          return
        }
      } else if (evt.event === 'complete') {
        logger.info('🎬 Backend received completion event')
        finalResult = evt.data
      } else if (evt.event === 'error') {
        logger.error(`❌ Backend received error event: ${(evt.data as any)?.error}`)
        send('error', evt.data as unknown as Record<string, unknown>)
        cleanup()
        if (!isStreamClosed(res)) res.end()
        return
      }
    }

    if (!finalResult) {
      logImageStreamTelemetry({
        partialCount,
        syntheticPartialUsed,
        status: 'failed',
        reason: 'no_final_result',
      })
      send('error', { error: 'Image generation produced no result' })
      cleanup()
      if (!isStreamClosed(res)) res.end()
      return
    }

    // Fallback for providers/modes that return only the final image frame:
    // synthesize a single "partial" event from the generated file so the
    // frontend can still show the morph stage instead of jumping straight to final.
    if (partialCount === 0) {
      try {
        const generatedPath = path.join(storageDir, finalResult.file_name)
        const imageBytes = await fs.readFile(generatedPath)
        const b64 = imageBytes.toString('base64')
        logger.info('🎬 Backend emitting synthetic partial from final image fallback')
        syntheticPartialUsed = send('partial', { b64, index: 0 })
      } catch (err) {
        logger.warn({ err }, 'failed to emit synthetic partial fallback')
      }
    }

    const finalized = await finalizeGeneratedImage({
      conversationId,
      question,
      userMessageId: userMsgId,
      result: finalResult,
      conversation: data.conversation,
      files: data.files,
      storageDir,
    })
    send('complete', {
      answer: finalized.answer,
      citations: finalized.citations,
      userMessageId: userMsgId,
      assistantMessageId: finalized.assistantMessageId,
      generatedImage: finalized.generatedImage,
    })
    logImageStreamTelemetry({
      partialCount,
      syntheticPartialUsed,
      status: 'completed',
    })
    cleanup()
    if (!isStreamClosed(res)) res.end()
  } catch (err) {
    if (upstreamAbort.signal.aborted) return
    logImageStreamTelemetry({
      partialCount,
      syntheticPartialUsed,
      status: 'failed',
      reason: err instanceof Error ? err.message : String(err),
    })
    logger.error({ err, conversationId }, 'generate-image-stream failed')
    send('error', { error: err instanceof Error ? err.message : String(err) })
    cleanup()
    if (!isStreamClosed(res)) res.end()
  }
})
