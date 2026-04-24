import Router from '@koa/router'
import path from 'node:path'
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

// File names are resolved against the conversation's storage dir server-side.
// We reject anything that could escape the storage dir (slashes, `..`) to
// prevent path traversal into unrelated files on disk.
const SAFE_FILE_NAME_RE = /^[^/\\]+$/

const imageGenSchema = z.object({
  conversationId: z.string().regex(SHORT_ID_RE),
  question: z.string().min(1),
  userId: z.number().int().min(0).optional(),
  referenceImageFileNames: z
    .array(z.string().regex(SAFE_FILE_NAME_RE).refine((n) => !n.includes('..'), 'invalid file name'))
    .max(4)
    .optional(),
})

export const imageGenRouter = new Router()

type ImageGenResult = {
  file_name: string
  revised_prompt: string
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
    revisedPrompt: string
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
  const answer = `![${title}](${imageUrl})\n\n<p class="image-caption">"${title}"${sourceMarkers}</p>`

  const assistantMsgId = await insertConversationMessage({
    conversationId,
    role: 'assistant',
    content: answer,
    citations: {
      _generatedImageDescription: result.revised_prompt || result.image_prompt,
      _imageSources: citations,
    },
  })

  try {
    const description = result.revised_prompt || result.image_prompt || title
    const sourceOriginalNames = files.map((f) => f.original_name)
    const imageId = await insertGeneratedImage({
      conversationId,
      messageId: assistantMsgId,
      storageNamespace: conversation.storage_namespace,
      fileName: result.file_name,
      imageTitle: result.image_title || title,
      imagePrompt: result.image_prompt || null,
      revisedPrompt: result.revised_prompt || null,
      userPrompt: question,
      description,
      sourceOriginalNames,
      sourceSizeBytes: files.map((f) => Number(f.size_bytes)),
    })
    await registerReusableImage({
      imageId,
      description,
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
      revisedPrompt: result.revised_prompt,
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

  const { conversationId, question, userId, referenceImageFileNames } = parsed.data

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
  // buttons like "Generate image inspired by: Screenshot 🎨" where the
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
    quality: 'auto',
    referenceImagePaths,
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
})

imageGenRouter.post('/announce-image', async (ctx) => {
  const parsed = announceImageSchema.safeParse(ctx.request.body)
  if (!parsed.success) {
    ctx.status = 400
    ctx.body = { error: 'Invalid request' }
    return
  }

  const { conversationId, question } = parsed.data

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

  const { conversationId, question, userId, referenceImageFileNames } = parsed.data

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
      signal: upstreamAbort.signal,
    })) {
      if (evt.event === 'prompt_ready') {
        if (!send('prompt_ready', evt.data as unknown as Record<string, unknown>)) return
      } else if (evt.event === 'partial') {
        if (!send('partial', evt.data as unknown as Record<string, unknown>)) return
      } else if (evt.event === 'complete') {
        finalResult = evt.data
      } else if (evt.event === 'error') {
        send('error', evt.data as unknown as Record<string, unknown>)
        cleanup()
        if (!isStreamClosed(res)) res.end()
        return
      }
    }

    if (!finalResult) {
      send('error', { error: 'Image generation produced no result' })
      cleanup()
      if (!isStreamClosed(res)) res.end()
      return
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
    cleanup()
    if (!isStreamClosed(res)) res.end()
  } catch (err) {
    if (upstreamAbort.signal.aborted) return
    logger.error({ err, conversationId }, 'generate-image-stream failed')
    send('error', { error: err instanceof Error ? err.message : String(err) })
    cleanup()
    if (!isStreamClosed(res)) res.end()
  }
})
