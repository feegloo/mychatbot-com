import Router from '@koa/router'
import multer from '@koa/multer'
import path from 'node:path'
import { z } from 'zod'
import { v4 as uuidv4 } from 'uuid'
import {
  getConversation,
  resolveConversationRole,
  insertUploadedFile,
  updateConversationStatus,
  createAccessRequest,
  getAccessRequest,
  approveAccessRequest,
  insertAccessToken,
  insertConversation,
  updateConversationDisplayName,
  getConversationSummaries,
  insertConversationMessage,
  getMessageById,
  updateFileMetadata,
  resolveUserByFingerprint,
  getThreadsForMessage,
  getThreadReplyCountsForMessages,
  getUploadedFilesByOriginalNames,
  getThreadsForConversation,
  getConversationThreadReplyCount,
} from '../repositories/conversations.js'
import { createStorageProvider } from '../storage/index.js'
import { generateShortId } from '../utils/id.js'
import { config } from '../config.js'
import { indexConversation, describeUrl } from '../python/indexing.js'
import { onConversationEvent } from '../events.js'
import { getConversationToken } from '../utils/request.js'
import { deriveToken } from '../security.js'
import { SHORT_ID_RE, MAX_FILE_SIZE } from '../constants.js'
import logger from '../logger.js'
import { bindStreamLifecycle, isStreamClosed } from '../utils/stream-lifecycle.js'

const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: MAX_FILE_SIZE } })
export const conversationsRouter = new Router()

// POST /conversations — create an empty conversation (no files required)
conversationsRouter.post('/conversations', async (ctx) => {
  const conversationId = generateShortId()
  const salt = uuidv4()
  const ownerPassword = deriveToken(conversationId, salt)
  const namespace = conversationId
  const collectionName = `conversation_${conversationId}`

  await insertConversation({
    id: conversationId,
    salt,
    display_name: null,
    status: 'ready',
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

  ctx.body = {
    conversationId,
    status: 'ready',
    url: `/c/${conversationId}`,
    ownerPassword,
  }
})

// Multiplexed SSE endpoint: one stream for multiple conversations.
// The client sends ?ids=id1,id2,... and receives all events for those conversations
// wrapped as: event: conversation_event / data: { conversationId, event, data }.
// The stream stays open indefinitely; keepalive pings prevent proxy timeouts.
conversationsRouter.get('/events', async (ctx) => {
  const idsParam = ctx.query.ids as string | string[] | undefined
  const raw = Array.isArray(idsParam) ? idsParam.join(',') : (idsParam ?? '')
  const requestedIds = raw.split(',').map((s) => s.trim()).filter(Boolean).slice(0, 30)

  if (requestedIds.length === 0) {
    ctx.status = 400
    ctx.body = { error: 'Missing ids parameter' }
    return
  }

  // Validate access in parallel — only subscribe to conversations that actually exist
  const checks = await Promise.all(
    requestedIds.map((id) =>
      getConversation(id, 'viewer')
        .then((d) => (d.conversation ? id : null))
        .catch(() => null),
    ),
  )
  const validIds = checks.filter((id): id is string => id !== null)

  if (validIds.length === 0) {
    ctx.status = 404
    ctx.body = { error: 'No valid conversations found' }
    return
  }

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
    'Access-Control-Allow-Origin': '*',
  })

  const unsubscribers: (() => void)[] = []
  let keepalive: NodeJS.Timeout | null = null

  const cleanup = bindStreamLifecycle(ctx.req, res, () => {
    unsubscribers.forEach((u) => u())
    if (keepalive) { clearInterval(keepalive); keepalive = null }
  })

  function sendFor(conversationId: string, event: string, payload: Record<string, unknown>): boolean {
    if (isStreamClosed(res)) { cleanup(); return false }
    try {
      res.write(
        `event: conversation_event\ndata: ${JSON.stringify({ conversationId, event, data: payload })}\n\n`,
      )
      return true
    } catch {
      cleanup()
      return false
    }
  }

  // Send catchup events so clients that reconnect pick up the latest state
  const conversationStates = await Promise.all(
    validIds.map((id) => getConversation(id, 'viewer').catch(() => null)),
  )

  for (let i = 0; i < validIds.length; i++) {
    const id = validIds[i]
    const data = conversationStates[i]
    if (!data?.conversation) continue

    if (data.conversation.status === 'ready') {
      if (!sendFor(id, 'welcome_message', {}) || !sendFor(id, 'complete', { status: 'ready' })) return
    } else if (data.conversation.status === 'failed') {
      // Don't close — other conversations in the batch may still be active
      if (!sendFor(id, 'complete', { status: 'failed' })) return
    } else {
      const hasWelcome = data.messages.some((m: { role: string }) => m.role === 'assistant')
      if (hasWelcome && !sendFor(id, 'welcome_message', {})) return
    }
  }

  if (isStreamClosed(res)) return

  // Subscribe to real-time events; unlike the single-conversation endpoint we
  // never close the stream on complete/error — other conversations may still fire.
  for (const id of validIds) {
    const unsub = onConversationEvent(id, (evt) => {
      sendFor(id, evt.event, evt.data)
    })
    unsubscribers.push(unsub)
  }

  keepalive = setInterval(() => {
    if (isStreamClosed(res)) { cleanup(); return }
    try { res.write(': keepalive\n\n') } catch { cleanup() }
  }, 15_000)
})

// SSE endpoint: stream processing events (welcome_message, complete) to the frontend
conversationsRouter.get('/conversations/:conversationId/events', async (ctx) => {
  const { conversationId } = ctx.params

  const data = await getConversation(conversationId, 'viewer')
  if (!data.conversation) {
    ctx.status = 404
    ctx.body = { error: 'Conversation not found' }
    return
  }

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
    'Access-Control-Allow-Origin': '*',
  })

  let unsubscribe = () => {}
  let keepalive: NodeJS.Timeout | null = null

  const cleanup = bindStreamLifecycle(ctx.req, res, () => {
    unsubscribe()
    if (keepalive) {
      clearInterval(keepalive)
      keepalive = null
    }
  })

  function send(event: string, payload: Record<string, unknown>): boolean {
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

  // If conversation has already reached a terminal state, send catchup events
  // so late-connecting clients refresh their indexing UI. For 'ready' convs we
  // keep the stream open so downstream `message_appended` events can flow
  // (enables real-time multi-tab message sync without 1s polling). For 'failed'
  // convs we close immediately since no more events are expected.
  if (data.conversation.status === 'ready') {
    if (!send('welcome_message', {}) || !send('complete', { status: 'ready' })) return
  } else if (data.conversation.status === 'failed') {
    send('complete', { status: 'failed' })
    res.end()
    return
  } else {
    // Processing: emit welcome catchup if already saved.
    const hasWelcome = data.messages.some((m: { role: string }) => m.role === 'assistant')
    if (hasWelcome && !send('welcome_message', {})) return
  }

  if (!send('connected', { conversationId })) return

  unsubscribe = onConversationEvent(conversationId, (evt) => {
    if (!send(evt.event, evt.data)) return
    if (evt.event === 'complete' || evt.event === 'error') {
      cleanup()
      if (!isStreamClosed(res)) res.end()
    }
  })

  keepalive = setInterval(() => {
    if (isStreamClosed(res)) {
      cleanup()
      return
    }

    try {
      res.write(': keepalive\n\n')
    } catch {
      cleanup()
    }
  }, 15_000)
})

conversationsRouter.get('/conversations/:conversationId', async (ctx) => {
  const conversationId = ctx.params.conversationId
  const token = getConversationToken(ctx)
  const role = await resolveConversationRole(conversationId, token)
  const data = await getConversation(conversationId, role)

  if (!data.conversation) {
    ctx.status = 404
    ctx.body = { error: 'Conversation not found' }
    return
  }

  // Gather thread reply counts for all assistant messages
  const assistantMessageIds = data.messages
    .filter((m) => m.role === 'assistant' && m.id)
    .map((m) => m.id)
  const threadCounts = await getThreadReplyCountsForMessages(assistantMessageIds)

  // Count conversation-level thread replies (from viewers branching shared conversations)
  const conversationThreadCount = await getConversationThreadReplyCount(conversationId)

  // For threads, storageNamespace differs from conversationId (points to parent's directory)
  const storageNamespace =
    data.conversation.storage_namespace !== data.conversation.id
      ? data.conversation.storage_namespace
      : undefined

  ctx.body = {
    conversationId: data.conversation.id,
    displayName: data.conversation.display_name || null,
    status: data.conversation.status,
    role,
    parentMessageId: data.conversation.parent_message_id || null,
    parentConversationId: data.conversation.parent_conversation_id || null,
    ...(storageNamespace ? { storageNamespace } : {}),
    ...(conversationThreadCount > 0 ? { conversationThreadCount } : {}),
    files: data.files.map((file) => ({
      id: file.id,
      originalName: file.original_name,
      mimeType: file.mime_type,
      sizeBytes: Number(file.size_bytes),
      metadata: file.metadata_json || null,
    })),
    messages: data.messages.map((message) => {
      const raw = message.citations_json
      const uploadedFileNames = raw && !Array.isArray(raw) ? raw._uploadedFileNames : undefined
      // Citations shapes:
      // - plain array: regular ask response
      // - { _imageSources }: dedicated image-gen response
      // - { citations, _imageSources }: auto-image appended to a regular answer
      const citations = Array.isArray(raw)
        ? raw
        : [...(raw?.citations || []), ...(raw?._imageSources || [])]
      const threadReplyCount = threadCounts.get(message.id) || 0
      // Mark the parent message (branched-from) in thread conversations
      const isParentMessage =
        data.conversation!.parent_message_id === message.id &&
        message.conversation_id !== data.conversation!.id
      // Suggested questions are now embedded as `[action:...]` markers
      // inside `message.content` itself (same format used for normal RAG
      // answers) — the frontend parses them from content. We keep the
      // `suggestedQuestions` field out entirely; older clients just show
      // the markers as text which is fine.
      return {
        id: message.id,
        role: message.role,
        content: message.content,
        citations,
        userId: message.user_id,
        ...(uploadedFileNames ? { uploadedFileNames } : {}),
        ...(threadReplyCount > 0 ? { threadReplyCount } : {}),
        ...(isParentMessage ? { isParentMessage: true } : {}),
      }
    }),
    suggestedQuestions: [] as string[],
    accessRequests: data.accessRequests.map((row) => ({
      id: row.id,
      displayName: row.display_name,
      status: row.status,
    })),
    errorMessage: data.conversation.error_message,
  }
})

conversationsRouter.post(
  '/conversations/:conversationId/files',
  upload.array('files'),
  async (ctx) => {
    const conversationId = ctx.params.conversationId
    const token = getConversationToken(ctx)
    const role = await resolveConversationRole(conversationId, token)
    const files = (ctx.files as multer.File[]) || []

    if (!files.length) {
      ctx.status = 400
      ctx.body = { error: 'No files uploaded' }
      return
    }

    const videoFiles = files.filter((f) => f.mimetype?.startsWith('video/'))
    if (videoFiles.length) {
      ctx.status = 400
      ctx.body = { error: 'Video files are not supported.' }
      return
    }

    if (role !== 'owner' && role !== 'editor') {
      ctx.status = 403
      ctx.body = { error: "You don't have permission to upload files" }
      return
    }

    const data = await getConversation(conversationId, role)

    if (!data.conversation) {
      ctx.status = 404
      ctx.body = { error: 'Conversation not found' }
      return
    }

    const storage = createStorageProvider()
    const namespace = data.conversation.storage_namespace
    const absolutePaths: string[] = []
    const uploadedFileNames: string[] = []
    const storedToOriginal: Record<string, string> = {}

    const existingNames = new Set(data.files.map((f) => f.original_name))
    const duplicates: string[] = []

    for (const file of files) {
      const originalName = Buffer.from(file.originalname, 'latin1')
        .toString('utf8')
        .normalize('NFC')

      if (existingNames.has(originalName)) {
        duplicates.push(originalName)
        continue
      }
      existingNames.add(originalName)

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
    }

    if (!absolutePaths.length) {
      ctx.status = 409
      ctx.body = { error: 'File already uploaded', duplicates }
      return
    }

    // Set status to processing while indexing
    await updateConversationStatus(conversationId, 'processing')

    indexConversation({
      conversationId,
      collectionName: data.conversation.vector_collection_name,
      files: absolutePaths,
    })
      .then(async (result) => {
        const welcomeMessage = result.parsedJson?.welcome_message || ''
        const fileMetadata = result.parsedJson?.file_metadata || {}
        if (welcomeMessage) {
          await insertConversationMessage({
            conversationId,
            role: 'assistant',
            content: welcomeMessage,
            citations: { _uploadedFileNames: uploadedFileNames },
          })
        }
        // Store file metadata per file
        for (const [fileName, metadata] of Object.entries(fileMetadata)) {
          try {
            const origName = storedToOriginal[fileName] || fileName
            await updateFileMetadata(conversationId, origName, metadata)
          } catch (err: any) {
            logger.error({ err, conversationId, fileName }, 'metadata update error')
          }
        }
        await updateConversationStatus(conversationId, 'ready')
      })
      .catch(async (error) => {
        logger.error({ err: error, conversationId }, 'indexing error')
        await updateConversationStatus(conversationId, 'failed', error.message)
      })

    ctx.body = {
      conversationId,
      status: 'processing',
      ...(duplicates.length ? { duplicates } : {}),
    }
  },
)

// POST /conversations/:conversationId/add-url
// Fetch a URL and add its HTML content to an existing conversation as a file
conversationsRouter.post('/conversations/:conversationId/add-url', async (ctx) => {
  const conversationId = ctx.params.conversationId
  const token = getConversationToken(ctx)
  const role = await resolveConversationRole(conversationId, token)

  if (role !== 'owner' && role !== 'editor') {
    ctx.status = 403
    ctx.body = { error: "You don't have permission to add URLs to this conversation" }
    return
  }

  const { url } = ctx.request.body as { url?: string }
  if (!url || typeof url !== 'string') {
    ctx.status = 400
    ctx.body = { error: 'No URL provided' }
    return
  }

  let parsed: URL
  try {
    parsed = new URL(url)
    if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error('Invalid protocol')
  } catch {
    ctx.status = 400
    ctx.body = { error: 'Invalid URL' }
    return
  }

  const data = await getConversation(conversationId, role)
  if (!data.conversation) {
    ctx.status = 404
    ctx.body = { error: 'Conversation not found' }
    return
  }

  await updateConversationStatus(conversationId, 'processing')

  describeUrl({
    url,
    conversationId,
    collectionName: data.conversation.vector_collection_name,
  })
    .then(async (result) => {
      const suggestedQuestions: string[] = result.parsedJson?.suggested_questions || []
      const welcomeMessage: string = result.parsedJson?.welcome_message || ''
      const fallbackMessage =
        welcomeMessage ||
        `## ${parsed.hostname}\n\nWebsite loaded and ready. Ask me anything about this page.`
      await insertConversationMessage({
        conversationId,
        role: 'assistant',
        content: fallbackMessage,
        citations: { _sourceUrl: url },
      })
      await updateConversationStatus(conversationId, 'ready')
    })
    .catch(async (error: Error) => {
      logger.error({ err: error.message, conversationId }, 'add-url indexing error')
      await updateConversationStatus(conversationId, 'failed', error.message)
    })

  ctx.body = { conversationId, status: 'processing' }
})

// POST /conversations/:conversationId/access-requests
// Viewer requests access to upload files
const requestAccessSchema = z.object({
  displayName: z.string().min(1),
})

conversationsRouter.post('/conversations/:conversationId/access-requests', async (ctx) => {
  const conversationId = ctx.params.conversationId
  const parsed = requestAccessSchema.safeParse(ctx.request.body)

  if (!parsed.success) {
    ctx.status = 400
    ctx.body = { error: 'Invalid request' }
    return
  }

  const { displayName } = parsed.data

  try {
    const data = await getConversation(conversationId)
    if (!data.conversation) {
      ctx.status = 404
      ctx.body = { error: 'Conversation not found' }
      return
    }

    const requestId = uuidv4()
    await createAccessRequest({
      id: requestId,
      conversation_id: conversationId,
      display_name: displayName,
      status: 'pending',
      editor_token: null,
    })

    ctx.body = { requestId, status: 'pending' }
  } catch (err: any) {
    logger.error({ err, conversationId }, 'access-request error')
    ctx.status = 500
    ctx.body = { error: 'Failed to create access request' }
  }
})

// GET /conversations/:conversationId/access-requests/:requestId
// Check if access request was approved
conversationsRouter.get(
  '/conversations/:conversationId/access-requests/:requestId',
  async (ctx) => {
    const conversationId = ctx.params.conversationId
    const requestId = ctx.params.requestId

    try {
      const request = await getAccessRequest(conversationId, requestId)

      if (!request) {
        ctx.status = 404
        ctx.body = { error: 'Access request not found' }
        return
      }

      ctx.body = {
        requestId: request.id,
        status: request.status,
        editorPassword: request.editor_token || null,
      }
    } catch (err: any) {
      logger.error({ err, conversationId, requestId }, 'get-access-request error')
      ctx.status = 500
      ctx.body = { error: 'Failed to get access request' }
    }
  },
)

// POST /conversations/:conversationId/access-requests/:requestId/approve
// Owner approves access request
conversationsRouter.post(
  '/conversations/:conversationId/access-requests/:requestId/approve',
  async (ctx) => {
    const conversationId = ctx.params.conversationId
    const requestId = ctx.params.requestId
    const token = getConversationToken(ctx)
    const role = await resolveConversationRole(conversationId, token)

    if (role !== 'owner') {
      ctx.status = 403
      ctx.body = { error: 'Only owner can approve access requests' }
      return
    }

    try {
      const request = await getAccessRequest(conversationId, requestId)

      if (!request) {
        ctx.status = 404
        ctx.body = { error: 'Access request not found' }
        return
      }

      if (request.status !== 'pending') {
        ctx.status = 400
        ctx.body = { error: `Cannot approve ${request.status} request` }
        return
      }

      // Get conversation to extract salt for deriving editor password
      const conv = await getConversation(conversationId, 'viewer')
      if (!conv.conversation) {
        ctx.status = 404
        ctx.body = { error: 'Conversation not found' }
        return
      }

      // Derive editor password from conversationId + salt + "editor" suffix
      const editorPassword = deriveToken(conversationId, `${conv.conversation.salt}:editor`)

      // Create access token for the requester with derived password
      await insertAccessToken({
        token: editorPassword,
        conversation_id: conversationId,
        role: 'editor',
      })

      // Mark request as approved with the password
      await approveAccessRequest(conversationId, requestId, editorPassword)

      ctx.body = { requestId, status: 'approved', editorPassword }
    } catch (err: any) {
      logger.error({ err, conversationId, requestId }, 'approve-access-request error')
      ctx.status = 500
      ctx.body = { error: 'Failed to approve access request' }
    }
  },
)

// PATCH /conversations/:conversationId/name
const renameSchema = z.object({
  displayName: z.string().min(1).max(200),
})

conversationsRouter.patch('/conversations/:conversationId/name', async (ctx) => {
  const conversationId = ctx.params.conversationId
  const token = getConversationToken(ctx)
  const role = await resolveConversationRole(conversationId, token)

  if (role !== 'owner' && role !== 'editor') {
    ctx.status = 403
    ctx.body = { error: 'Only owner or editor can rename conversations' }
    return
  }

  const parsed = renameSchema.safeParse(ctx.request.body)
  if (!parsed.success) {
    ctx.status = 400
    ctx.body = { error: 'Invalid display name' }
    return
  }

  await updateConversationDisplayName(conversationId, parsed.data.displayName)
  ctx.body = { displayName: parsed.data.displayName }
})

const batchSchema = z.object({
  conversationIds: z.array(z.string().regex(/^[0-9A-Za-z-]{16,36}$/)),
})

conversationsRouter.post('/conversations/batch', async (ctx) => {
  const parsed = batchSchema.safeParse(ctx.request.body)
  if (!parsed.success) {
    ctx.status = 400
    ctx.body = { error: 'Invalid request body' }
    return
  }

  const summaries = await getConversationSummaries(parsed.data.conversationIds)

  const results = summaries.map((row) => ({
    conversationId: row.id,
    displayName: row.display_name || null,
    status: row.status,
    fileNames: row.fileNames,
  }))

  ctx.body = { conversations: results }
})

conversationsRouter.get('/messages/:messageId', async (ctx) => {
  const messageId = ctx.params.messageId
  if (!SHORT_ID_RE.test(messageId)) {
    ctx.status = 400
    ctx.body = { error: 'Invalid message ID' }
    return
  }

  const msg = await getMessageById(messageId)
  if (!msg || msg.role !== 'assistant') {
    ctx.status = 404
    ctx.body = { error: 'Message not found' }
    return
  }

  const raw = msg.citations_json
  const uploadedFileNames =
    raw && !Array.isArray(raw) && Array.isArray(raw._uploadedFileNames)
      ? raw._uploadedFileNames.filter((name: unknown): name is string => typeof name === 'string')
      : undefined
  const citations = Array.isArray(raw)
    ? raw
    : [...(raw?.citations || []), ...(raw?._imageSources || [])]
  let files:
    | Array<{
        id: string
        originalName: string
        mimeType: string
        sizeBytes: number
        metadata: any | null
      }>
    | undefined
  if (uploadedFileNames?.length) {
    const uploadedFiles = await getUploadedFilesByOriginalNames(
      msg.conversation_id,
      uploadedFileNames,
    )
    const byName = new Map(uploadedFiles.map((f) => [f.original_name, f]))
    files = uploadedFileNames
      .map((name: string) => byName.get(name))
      .filter(
        (f: (typeof uploadedFiles)[number] | undefined): f is (typeof uploadedFiles)[number] => !!f,
      )
      .map((f: (typeof uploadedFiles)[number]) => ({
        id: f.id,
        originalName: f.original_name,
        mimeType: f.mime_type,
        sizeBytes: Number(f.size_bytes),
        metadata: f.metadata_json || null,
      }))
  }
  ctx.body = {
    id: msg.id,
    conversationId: msg.conversation_id,
    displayName: msg.display_name || null,
    role: msg.role,
    content: msg.content,
    citations,
    ...(uploadedFileNames ? { uploadedFileNames } : {}),
    ...(files?.length ? { files } : {}),
  }
})

// POST /fingerprint — resolve browser fingerprint to userId
const fingerprintSchema = z.object({
  fingerprint: z.string().min(8).max(128),
})

conversationsRouter.post('/fingerprint', async (ctx) => {
  const parsed = fingerprintSchema.safeParse(ctx.request.body)
  if (!parsed.success) {
    ctx.status = 400
    ctx.body = { error: 'Invalid fingerprint' }
    return
  }
  const userAgent = ctx.get('User-Agent') || undefined
  const userId = await resolveUserByFingerprint(parsed.data.fingerprint, userAgent)
  ctx.body = { userId }
})

// GET /messages/:messageId/threads — get all thread conversations for a shared message
conversationsRouter.get('/messages/:messageId/threads', async (ctx) => {
  const messageId = ctx.params.messageId
  if (!SHORT_ID_RE.test(messageId)) {
    ctx.status = 400
    ctx.body = { error: 'Invalid message ID' }
    return
  }

  const threads = await getThreadsForMessage(messageId)
  ctx.body = {
    threads: threads.map((t) => ({
      conversationId: t.id,
      displayName: t.display_name,
      messageCount: (t as any).message_count || 0,
      lastUserId: (t as any).last_user_id || 0,
    })),
  }
})

// POST /messages/:messageId/threads — create a new thread conversation from a shared message
const createThreadSchema = z.object({
  userId: z.number().int().min(1),
})

conversationsRouter.post('/messages/:messageId/threads', async (ctx) => {
  const messageId = ctx.params.messageId
  if (!SHORT_ID_RE.test(messageId)) {
    ctx.status = 400
    ctx.body = { error: 'Invalid message ID' }
    return
  }

  const parsed = createThreadSchema.safeParse(ctx.request.body)
  if (!parsed.success) {
    ctx.status = 400
    ctx.body = { error: 'Invalid request' }
    return
  }

  // Verify parent message exists
  const parentMsg = await getMessageById(messageId)
  if (!parentMsg) {
    ctx.status = 404
    ctx.body = { error: 'Parent message not found' }
    return
  }

  // Get the parent conversation to copy its vector collection for RAG
  const parentConv = await getConversation(parentMsg.conversation_id)
  if (!parentConv.conversation) {
    ctx.status = 404
    ctx.body = { error: 'Parent conversation not found' }
    return
  }

  // Create thread conversation
  const threadId = generateShortId()
  const salt = uuidv4()
  const ownerPassword = deriveToken(threadId, salt)

  await insertConversation({
    id: threadId,
    salt,
    display_name: null,
    status: 'ready',
    storage_namespace: parentConv.conversation.storage_namespace,
    vector_collection_name: parentConv.conversation.vector_collection_name,
    indexing_mode: parentConv.conversation.indexing_mode,
    error_message: null,
    parent_message_id: messageId,
    parent_conversation_id: null,
  })

  await insertAccessToken({
    token: ownerPassword,
    conversation_id: threadId,
    role: 'owner',
  })

  ctx.body = {
    conversationId: threadId,
    ownerPassword,
    url: `/c/${threadId}`,
  }
})

// GET /conversations/:conversationId/threads — get all thread conversations branched from a shared conversation
conversationsRouter.get('/conversations/:conversationId/threads', async (ctx) => {
  const conversationId = ctx.params.conversationId

  const threads = await getThreadsForConversation(conversationId)
  ctx.body = {
    threads: threads.map((t) => ({
      conversationId: t.id,
      displayName: t.display_name,
      messageCount: (t as any).message_count || 0,
      lastUserId: (t as any).last_user_id || 0,
    })),
  }
})

// POST /conversations/:conversationId/threads — create a new thread from a shared conversation (viewer reply)
const createConvThreadSchema = z.object({
  userId: z.number().int().min(1),
})

conversationsRouter.post('/conversations/:conversationId/threads', async (ctx) => {
  const conversationId = ctx.params.conversationId

  const parsed = createConvThreadSchema.safeParse(ctx.request.body)
  if (!parsed.success) {
    ctx.status = 400
    ctx.body = { error: 'Invalid request' }
    return
  }

  // Get the parent conversation
  const parentConv = await getConversation(conversationId)
  if (!parentConv.conversation) {
    ctx.status = 404
    ctx.body = { error: 'Conversation not found' }
    return
  }

  // Create thread conversation
  const threadId = generateShortId()
  const salt = uuidv4()
  const ownerPassword = deriveToken(threadId, salt)

  await insertConversation({
    id: threadId,
    salt,
    display_name: null,
    status: 'ready',
    storage_namespace: parentConv.conversation.storage_namespace,
    vector_collection_name: parentConv.conversation.vector_collection_name,
    indexing_mode: parentConv.conversation.indexing_mode,
    error_message: null,
    parent_message_id: null,
    parent_conversation_id: conversationId,
  })

  await insertAccessToken({
    token: ownerPassword,
    conversation_id: threadId,
    role: 'owner',
  })

  ctx.body = {
    conversationId: threadId,
    ownerPassword,
    url: `/c/${threadId}`,
  }
})
