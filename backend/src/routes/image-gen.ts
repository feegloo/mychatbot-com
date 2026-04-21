import Router from '@koa/router'
import path from 'node:path'
import { z } from 'zod'
import {
  getConversation,
  insertConversationMessage,
  resolveConversationRole,
} from '../repositories/conversations.js'
import { generateImage } from '../python/image-gen.js'
import { buildChatHistory, getWelcomeMessages } from '../utils/chat-history.js'
import { config } from '../config.js'
import { getConversationToken } from '../utils/request.js'
import { SHORT_ID_RE } from '../constants.js'

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

  const referenceImagePaths = (referenceImageFileNames || []).map((name) =>
    path.join(storageDir, name),
  )

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

  // Build the assistant answer with the image
  const imageUrl = `/api/storage/${conversationId}/${result.file_name}`
  const title = result.image_title || 'Generated Image'

  // Map RAG sources returned by the model to citation objects
  const citations = (result.rag_sources || []).map((s) => ({
    fileName: s.file_name,
    chunkId: s.chunk_id,
    text: s.text,
    section: s.section ?? null,
    page: s.page ?? null,
  }))

  // Append [1][2]... source markers to the caption so they render as clickable source buttons
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

  ctx.body = {
    answer,
    citations,
    userMessageId: userMsgId,
    assistantMessageId: assistantMsgId,
    generatedImage: {
      fileName: result.file_name,
      imagePrompt: result.image_prompt,
      revisedPrompt: result.revised_prompt,
      imageTitle: result.image_title,
    },
  }
})
