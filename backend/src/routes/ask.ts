import Router from '@koa/router'
import path from 'node:path'
import { z } from 'zod'
import * as Sentry from '@sentry/node'
import {
  getConversation,
  insertConversationMessage,
  resolveConversationRole,
} from '../repositories/conversations.js'
import { answerQuestion } from '../python/answering.js'
import { ensureCollectionIndexed } from '../python/reindex.js'
import { buildChatHistory, getWelcomeMessages } from '../utils/chat-history.js'
import { config } from '../config.js'
import { getConversationToken } from '../utils/request.js'
import { IMAGE_EXTENSIONS, SHORT_ID_RE } from '../constants.js'
import logger from '../logger.js'

const askSchema = z.object({
  conversationId: z.string().regex(SHORT_ID_RE),
  question: z.string().min(1),
  userId: z.number().int().min(0).optional(),
})

export const askRouter = new Router()

askRouter.post('/ask', async (ctx) => {
  const parsed = askSchema.safeParse(ctx.request.body)
  if (!parsed.success) {
    ctx.status = 400
    ctx.body = { error: 'Invalid request' }
    return
  }

  const { conversationId, question, userId } = parsed.data

  // Only owners/editors can post questions
  const token = getConversationToken(ctx)
  const role = await resolveConversationRole(conversationId, token)
  if (role !== 'owner' && role !== 'editor') {
    ctx.status = 403
    ctx.body = { error: 'Only the conversation owner can reply' }
    return
  }

  const data = await getConversation(conversationId)

  if (!data.conversation) {
    ctx.status = 404
    ctx.body = { error: 'Conversation not found' }
    return
  }

  if (data.conversation.status !== 'ready') {
    ctx.status = 409
    ctx.body = { error: 'Conversation is not ready yet', status: data.conversation.status }
    return
  }

  const userMsgId = await insertConversationMessage({
    conversationId,
    role: 'user',
    content: question,
    userId: userId || 0,
  })

  // Ensure vector collection has data (re-index if Chroma was lost on container restart)
  await ensureCollectionIndexed(
    conversationId,
    data.conversation.vector_collection_name,
    data.conversation.storage_namespace,
  )

  const chatHistory = buildChatHistory(data.messages)
  // For threads, use parent's welcome messages (file descriptions) as context;
  // for normal conversations, extract from the conversation's own messages.
  const welcomeMessages = data.parentWelcomeContents.length
    ? data.parentWelcomeContents
    : getWelcomeMessages(data.messages)

  // Resolve image file paths and metadata for Vision API (used on "recognize person name")
  const imageFilePaths = data.files
    .filter((f) => IMAGE_EXTENSIONS.has(path.extname(f.original_name).toLowerCase()))
    .map((f) => path.join(config.storageRoot, f.storage_key))
  const fileMetadata: Record<string, any> = {}
  for (const f of data.files) {
    if (f.metadata_json) fileMetadata[f.original_name] = f.metadata_json
  }

  logger.info(
    { conversationId, questionLen: question.length, imageFiles: imageFilePaths.length, metadataKeys: Object.keys(fileMetadata) },
    'ask request',
  )
  if (imageFilePaths.length) {
    logger.debug({ imageFilePaths }, 'ask image file paths')
  }

  Sentry.logger.info(Sentry.logger.fmt`Ask request for conversation ${conversationId}`, {
    conversation_id: conversationId,
    question_length: question.length,
    image_file_count: imageFilePaths.length,
    metadata_keys: Object.keys(fileMetadata).join(',') || 'none',
    collection_name: data.conversation.vector_collection_name,
  })

  const storageDir = path.join(config.storageRoot, data.conversation.storage_namespace)

  // Collect all previously shown suggested questions:
  // 1. Indexing-time suggested questions from DB
  const previousSuggestedQuestions: string[] = data.suggestedQuestions.map((q) => q.question)
  // 2. Action buttons extracted from previous assistant messages ([action:Label])
  const actionRegex = /\[action:\s*([^\]]+)\]/g
  for (const msg of data.messages) {
    if (msg.role === 'assistant' && msg.content) {
      let match
      while ((match = actionRegex.exec(msg.content)) !== null) {
        previousSuggestedQuestions.push(match[1].trim())
      }
      actionRegex.lastIndex = 0
    }
  }

  const result = await answerQuestion({
    conversationId,
    collectionName: data.conversation.vector_collection_name,
    question,
    chatHistory,
    welcomeMessages,
    imageFilePaths: imageFilePaths.length ? imageFilePaths : undefined,
    fileMetadata: Object.keys(fileMetadata).length ? fileMetadata : undefined,
    storageDir,
    previousSuggestedQuestions: previousSuggestedQuestions.length
      ? previousSuggestedQuestions
      : undefined,
    conversationName: data.conversation.display_name || undefined,
  })

  const payload = result.parsedJson || {
    answer: result.stdout,
    citations: [],
  }

  Sentry.logger.info(Sentry.logger.fmt`Answer generated for conversation ${conversationId}`, {
    conversation_id: conversationId,
    answer_length: (payload.answer || '').length,
    citation_count: Array.isArray(payload.citations) ? payload.citations.length : 0,
  })

  const assistantMsgId = await insertConversationMessage({
    conversationId,
    role: 'assistant',
    content: payload.answer || '',
    citations: payload.citations || [],
  })

  ctx.body = { ...payload, userMessageId: userMsgId, assistantMessageId: assistantMsgId }
})
