import axios, { AxiosError } from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
})

/** Read the HTTP status from any error (axios or otherwise), if present. */
export function httpStatus(err: unknown): number | undefined {
  return (err as { response?: { status?: number } } | undefined)?.response?.status
}

/** Extract a user-friendly message + raw debug string from any error (axios or otherwise). */
export function extractError(err: unknown): { message: string; raw: string } {
  const e = err as Record<string, unknown> | undefined
  const resp = (e?.response ?? {}) as Record<string, unknown>
  const status = resp.status as number | undefined
  const data = resp.data as Record<string, string> | undefined
  const message = data?.error || data?.msg || (e?.message as string) || 'Unknown error'
  const parts: string[] = []
  if (status) parts.push(`HTTP ${status}`)
  parts.push(message)
  if (data?.stack) parts.push(`\n${data.stack}`)
  else if (e?.stack && !data) parts.push(`\n${e.stack}`)
  return { message, raw: parts.join(' — ') }
}

const TOKENS_STORAGE_KEY = 'conversation-token'

type TokensMap = {
  [conversationId: string]: string
}

function getTokensMap(): TokensMap {
  try {
    const stored = localStorage.getItem(TOKENS_STORAGE_KEY)
    return stored ? JSON.parse(stored) : {}
  } catch {
    return {}
  }
}

function saveTokensMap(tokens: TokensMap) {
  localStorage.setItem(TOKENS_STORAGE_KEY, JSON.stringify(tokens))
}

export function saveConversationToken(conversationId: string, token: string) {
  const tokens = getTokensMap()
  tokens[conversationId] = token
  saveTokensMap(tokens)
}

export function getConversationToken(conversationId: string) {
  const tokens = getTokensMap()
  return tokens[conversationId] || ''
}

export function getStoredConversationIds(): string[] {
  return Object.keys(getTokensMap())
}

export type ConversationSummary = {
  conversationId: string
  displayName: string | null
  status: 'processing' | 'ready' | 'failed'
  fileNames: string[]
}

export async function listMyConversations(): Promise<ConversationSummary[]> {
  const tokens = getTokensMap()
  const ids = Object.keys(tokens)
  if (!ids.length) return []

  const response = await api.post('/conversations/batch', { conversationIds: ids })
  const conversations = (response.data as { conversations: ConversationSummary[] }).conversations

  // Remove stale tokens for conversations that no longer exist in the DB.
  // Skip cleanup if server returned nothing — likely a transient backend/DB failure.
  const returnedIds = new Set(conversations.map((c) => c.conversationId))
  const staleIds = ids.filter((id) => !returnedIds.has(id))
  if (staleIds.length && returnedIds.size > 0) {
    const updated = getTokensMap()
    for (const id of staleIds) delete updated[id]
    saveTokensMap(updated)
  }

  return conversations
}

function authHeaders(conversationId: string) {
  const token = getConversationToken(conversationId)
  return token ? { 'x-conversation-token': token } : {}
}

export type ChatMessage = {
  id?: string
  role: 'user' | 'assistant'
  content: string
  citations?: Array<{
    fileName: string
    chunkId: string
    text: string
    section?: string
    page?: number | null
    imageName?: string
  }>
  uploadedFileNames?: string[]
  userId?: number
  threadReplyCount?: number
  isParentMessage?: boolean
  /** Set to true while an image is being generated, to show the animated loading state. */
  generatingImage?: boolean
  /** One-sentence teaser shown under the typing indicator while the image
   *  is being generated (populated by a quick LLM call). */
  imageAnnouncement?: string
  /** Detailed image prompt prepared by LLM and emitted by `prompt_ready`. */
  imageDetailedPrompt?: string
  /** Human-friendly title received from image generation events/final payload. */
  imageTitle?: string
  /** Latest partial (progressive) image frame as a data URL, shown blurred
   *  while generation is in progress and cross-fades into the final image. */
  imagePartialDataUrl?: string
  /** Index of the latest partial frame (0-based). Used to decrease blur
   *  intensity per successive frame so the image visually sharpens. */
  imagePartialIndex?: number
}

export type ConversationStatus = {
  conversationId: string
  displayName: string | null
  status: 'processing' | 'ready' | 'failed'
  role: 'owner' | 'editor' | 'viewer'
  parentMessageId: string | null
  parentConversationId: string | null
  storageNamespace?: string
  conversationThreadCount?: number
  files: Array<{
    id: string
    originalName: string
    mimeType: string
    sizeBytes: number
    metadata?: Record<string, unknown>
  }>
  messages: ChatMessage[]
  accessRequests: Array<{
    id: string
    displayName: string
    status: 'pending' | 'approved' | 'rejected'
  }>
  errorMessage?: string | null
}

export async function uploadFiles(files: File[]) {
  const DIRECT_UPLOAD_THRESHOLD = 30 * 1024 * 1024 // 30 MB
  const hasLargeFile = files.some((f) => f.size > DIRECT_UPLOAD_THRESHOLD)

  // For large files, use direct-to-GCS upload to bypass Cloud Run's 32 MiB proxy limit
  if (hasLargeFile) {
    try {
      return await uploadFilesViaSignedUrl(files)
    } catch (err: unknown) {
      // If signed-url endpoint returns 400 (not GCS), fall through to normal upload
      if (err instanceof AxiosError && err.response?.status === 400) {
        // fall through
      } else {
        throw err
      }
    }
  }

  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))
  const response = await api.post('/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return response.data as {
    conversationId: string
    url: string
    status: string
    ownerPassword: string
  }
}

async function uploadFilesViaSignedUrl(files: File[]) {
  // Step 1: Get signed URLs from backend (small JSON request)
  const fileMeta = files.map((f) => ({
    name: f.name,
    mimeType: f.type || 'application/octet-stream',
    size: f.size,
  }))
  const initResponse = await api.post('/upload/signed-url', { files: fileMeta })
  const { conversationId, ownerPassword, url, signedUrls } = initResponse.data as {
    conversationId: string
    ownerPassword: string
    url: string
    signedUrls: Array<{ name: string; signedUrl: string; gcsKey: string; storedName: string }>
  }

  // Step 2: Upload each file directly to GCS using the signed resumable URL
  for (let i = 0; i < files.length; i++) {
    const file = files[i]
    const { signedUrl } = signedUrls[i]

    // Initiate resumable upload session
    const sessionResponse = await fetch(signedUrl, {
      method: 'POST',
      headers: {
        'Content-Type': file.type || 'application/octet-stream',
        'x-goog-resumable': 'start',
      },
    })

    const sessionUri = sessionResponse.headers.get('Location')
    if (!sessionUri) throw new Error(`Failed to initiate resumable upload for ${file.name}`)

    // Upload the file content to the session URI
    await fetch(sessionUri, {
      method: 'PUT',
      headers: {
        'Content-Type': file.type || 'application/octet-stream',
      },
      body: file,
    })
  }

  // Step 3: Tell backend files are uploaded, start indexing
  const finalizePayload = {
    conversationId,
    files: signedUrls.map((s, i) => ({
      name: s.name,
      mimeType: files[i].type || 'application/octet-stream',
      size: files[i].size,
      gcsKey: s.gcsKey,
      storedName: s.storedName,
    })),
  }
  await api.post('/upload/finalize', finalizePayload, {
    headers: { 'x-conversation-token': ownerPassword },
  })

  return { conversationId, url, status: 'processing', ownerPassword }
}

export async function uploadUrl(url: string) {
  const response = await api.post('/upload-url', { url })
  return response.data as {
    conversationId: string
    url: string
    status: string
    ownerPassword: string
  }
}

export async function createConversation() {
  const response = await api.post('/conversations')
  return response.data as {
    conversationId: string
    url: string
    status: string
    ownerPassword: string
  }
}

export async function addUrlToConversation(conversationId: string, url: string) {
  const response = await api.post(
    `/conversations/${conversationId}/add-url`,
    { url },
    { headers: authHeaders(conversationId) },
  )
  return response.data as { conversationId: string; status: string }
}

export async function uploadMoreFiles(conversationId: string, files: File[]) {
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))
  const response = await api.post(`/conversations/${conversationId}/files`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
      ...authHeaders(conversationId),
    },
  })
  return response.data as { conversationId: string; status: string }
}

export async function getConversation(conversationId: string) {
  const response = await api.get(`/conversations/${conversationId}`, {
    headers: authHeaders(conversationId),
  })
  return response.data as ConversationStatus
}

export async function askQuestion(
  conversationId: string,
  question: string,
  userId?: number,
  language?: string,
) {
  const response = await api.post(
    '/ask',
    { conversationId, question, ...(userId ? { userId } : {}), ...(language ? { language } : {}) },
    {
      headers: authHeaders(conversationId),
    },
  )
  return response.data as {
    answer: string
    citations: Array<{
      fileName: string
      chunkId: string
      text: string
      section?: string
      page?: number | null
    }>
    userMessageId?: string
    assistantMessageId?: string
  }
}

export async function generateImage(
  conversationId: string,
  question: string,
  userId?: number,
  language?: string,
) {
  const response = await api.post(
    '/generate-image',
    { conversationId, question, ...(userId ? { userId } : {}), ...(language ? { language } : {}) },
    {
      headers: authHeaders(conversationId),
    },
  )
  return response.data as {
    answer: string
    citations: Array<{
      fileName: string
      chunkId: string
      text: string
      section?: string
      page?: number | null
    }>
    userMessageId?: string
    assistantMessageId?: string
    generatedImage?: {
      fileName: string
      imagePrompt: string
      revisedPrompt: string
    }
  }
}

export async function announceImage(conversationId: string, question: string, language?: string) {
  const response = await api.post(
    '/announce-image',
    { conversationId, question, ...(language ? { language } : {}) },
    {
      headers: authHeaders(conversationId),
    },
  )
  return response.data as { announcement: string }
}

export type ImageGenStreamCallbacks = {
  onUserMessage?: (userMessageId: string) => void
  onPromptReady?: (data: { image_prompt: string; image_title: string }) => void
  onPartial?: (data: { b64: string; index: number }) => void
  onComplete: (data: {
    answer: string
    citations: Array<{
      fileName: string
      chunkId: string
      text: string
      section?: string
      page?: number | null
    }>
    userMessageId?: string
    assistantMessageId?: string
    generatedImage?: {
      fileName: string
      imagePrompt: string
      revisedPrompt: string
      imageTitle: string
    }
  }) => void
  onError?: (message: string) => void
  signal?: AbortSignal
}

/**
 * Streams progressive image-generation events from `/generate-image-stream`.
 * Parses the SSE protocol (`event: name\ndata: {json}\n\n`) and dispatches
 * to the provided callbacks. Resolves when the stream ends.
 *
 * Fetch + ReadableStream is used instead of axios because axios does not
 * expose incremental body chunks in the browser.
 */
export async function generateImageStream(
  conversationId: string,
  question: string,
  userId: number | undefined,
  callbacks: ImageGenStreamCallbacks,
  language?: string,
  referenceImageFileNames?: string[],
): Promise<void> {
  const eventSeparator = /\r?\n\r?\n/
  let eventCount = 0
  const dispatchEvent = (rawEvent: string) => {
    let eventName = 'message'
    let dataLine = ''
    for (const line of rawEvent.split(/\r?\n/)) {
      if (line.startsWith('event: ')) eventName = line.slice(7).trim()
      else if (line.startsWith('data: ')) dataLine += line.slice(6)
    }
    if (!dataLine) {
      console.debug('🎬 Frontend: Skipping empty event', { rawEvent })
      return
    }

    let payload: unknown
    try {
      payload = JSON.parse(dataLine)
    } catch (e) {
      console.error('🎬 Frontend: Failed to parse JSON', { dataLine, error: e })
      return
    }
    eventCount++
    console.log(`🎬 Frontend: Dispatching event #${eventCount} (type=${eventName})`, { payload })
    if (eventName === 'user_message') {
      callbacks.onUserMessage?.((payload as { userMessageId: string }).userMessageId)
    } else if (eventName === 'prompt_ready') {
      callbacks.onPromptReady?.(payload as { image_prompt: string; image_title: string })
    } else if (eventName === 'partial') {
      console.log(`🎬 Frontend: Calling onPartial callback for index=${(payload as any)?.index}`)
      callbacks.onPartial?.(payload as { b64: string; index: number })
    } else if (eventName === 'complete') {
      callbacks.onComplete(payload as Parameters<ImageGenStreamCallbacks['onComplete']>[0])
    } else if (eventName === 'error') {
      callbacks.onError?.((payload as { error: string }).error)
    }
  }

  const consumeBufferedEvents = () => {
    let match = buffer.match(eventSeparator)
    while (match && match.index !== undefined) {
      const rawEvent = buffer.slice(0, match.index)
      buffer = buffer.slice(match.index + match[0].length)
      dispatchEvent(rawEvent)
      match = buffer.match(eventSeparator)
    }
  }

  const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  }
  const authToken = authHeaders(conversationId)
  if ('x-conversation-token' in authToken) {
    headers['x-conversation-token'] = authToken['x-conversation-token'] as string
  }
  const response = await fetch(`${baseUrl}/generate-image-stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      conversationId,
      question,
      ...(userId ? { userId } : {}),
      ...(language ? { language } : {}),
      ...(referenceImageFileNames?.length ? { referenceImageFileNames } : {}),
    }),
    signal: callbacks.signal,
    credentials: 'include',
  })
  if (!response.ok || !response.body) {
    const text = await response.text().catch(() => '')
    throw new Error(`Image stream failed (${response.status}): ${text}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    consumeBufferedEvents()
  }

  const trailingEvent = buffer.trim()
  if (trailingEvent) dispatchEvent(trailingEvent)
}

function getBaseUrl() {
  return (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/api$/, '')
}

export function getStorageUrl(conversationId: string, fileName: string) {
  return `${getBaseUrl()}/api/storage/${conversationId}/${encodeURIComponent(fileName)}`
}

/**
 * Resolve a stable same-origin URL for a stored file.
 *
 * The backend returns `/api/storage/:conversationId/:fileName` so PDF and image
 * previews can always embed a local proxy URL instead of expiring signed links.
 */
export async function resolveStorageUrl(conversationId: string, fileName: string) {
  const response = await api.get(`/storage/${conversationId}/${encodeURIComponent(fileName)}/url`)
  return (response.data as { url: string }).url
}

export async function requestUploadAccess(conversationId: string, displayName: string) {
  const response = await api.post(`/conversations/${conversationId}/access-requests`, {
    displayName,
  })
  return response.data as { requestId: string; status: 'pending' }
}

export async function getUploadAccessRequest(conversationId: string, requestId: string) {
  const response = await api.get(`/conversations/${conversationId}/access-requests/${requestId}`)
  return response.data as {
    requestId: string
    status: 'pending' | 'approved' | 'rejected'
    editorPassword: string | null
  }
}

export async function approveUploadAccess(conversationId: string, requestId: string) {
  const response = await api.post(
    `/conversations/${conversationId}/access-requests/${requestId}/approve`,
    {},
    { headers: authHeaders(conversationId) },
  )
  return response.data as { requestId: string; status: 'approved' }
}

export async function renameConversation(conversationId: string, displayName: string) {
  const response = await api.patch(
    `/conversations/${conversationId}/name`,
    { displayName },
    { headers: authHeaders(conversationId) },
  )
  return response.data as { displayName: string }
}

export type SharedMessage = {
  id: string
  conversationId: string
  displayName: string | null
  role: 'assistant'
  content: string
  citations: ChatMessage['citations']
  uploadedFileNames?: string[]
  files?: ConversationStatus['files']
}

export async function getSharedMessage(messageId: string) {
  const response = await api.get(`/messages/${messageId}`)
  return response.data as SharedMessage
}

export type DebugTableName =
  | 'conversations'
  | 'conversation_messages'
  | 'suggested_questions'
  | 'uploaded_files'
  | 'user_fingerprints'
  | 'conversation_access_tokens'
  | 'access_requests'
  | 'users'
  | 'processing_jobs'
  | 'processing_jobs_errors'
  | 'prompt_history'
  | 'generated_images'
  | 'indexing_events'
  | 'pdf_pages'
  | 'workers'
  | 'jobs'
  | 'user_wikis'

export async function getDebugTablesOverview(username: string, password: string) {
  const response = await api.get('/debug/tables-overview', {
    auth: { username, password },
  })
  return response.data as {
    counts: Record<DebugTableName, number>
    conversations: Record<string, unknown>[]
  }
}

export async function getDebugTable(
  username: string,
  password: string,
  name: DebugTableName,
  offset = 0,
) {
  const response = await api.get(`/debug/tables/${name}`, {
    auth: { username, password },
    params: { offset },
  })
  return response.data as { rows: Record<string, unknown>[] }
}

export async function getFullPrompt(username: string, password: string, promptId: string) {
  const response = await api.get(`/debug/prompt-full/${promptId}`, {
    auth: { username, password },
  })
  return response.data as { prompt_text: string; response_text: string }
}

export async function runDebugSql(username: string, password: string, sql: string) {
  const response = await api.post('/debug/sql', { sql }, { auth: { username, password } })
  return response.data as {
    rows: Record<string, unknown>[]
    fields: string[]
    rowCount: number | null
    command: string
    durationMs: number
  }
}

export async function translateTexts(texts: string[], targetLang: string, sourceLang?: string) {
  const body: { texts: string[]; targetLang: string; sourceLang?: string } = { texts, targetLang }
  if (sourceLang) body.sourceLang = sourceLang
  const response = await api.post('/translate', body)
  return response.data as { translations: string[] }
}

export async function detectLanguage(text: string) {
  const response = await api.post('/detect-language', { text })
  return response.data as { language: string; confidence: number }
}

export async function synthesizeSpeech(
  text: string,
  language?: string,
  instructions?: string,
): Promise<Blob> {
  const body: { text: string; language?: string; instructions?: string } = { text }
  if (language) body.language = language
  if (instructions) body.instructions = instructions
  const response = await api.post('/synthesize', body, {
    responseType: 'blob',
  })
  return response.data as Blob
}

export type WordCaption = {
  word: string
  start: number
  end: number
}

export async function synthesizeSpeechWithCaptions(
  text: string,
  language?: string,
  translateTo?: string,
  instructions?: string,
): Promise<{ audio: Blob; captions: WordCaption[] | null; translatedText?: string }> {
  const body: { text: string; language?: string; translateTo?: string; instructions?: string } = {
    text,
  }
  if (language) body.language = language
  if (translateTo) body.translateTo = translateTo
  if (instructions) body.instructions = instructions

  const response = await api.post('/synthesize-with-captions', body)
  const data = response.data as {
    audio: string
    captions: WordCaption[] | null
    translatedText?: string
  }

  // Decode base64 audio to Blob
  const binaryStr = atob(data.audio)
  const bytes = new Uint8Array(binaryStr.length)
  for (let i = 0; i < binaryStr.length; i++) {
    bytes[i] = binaryStr.charCodeAt(i)
  }

  return {
    audio: new Blob([bytes], { type: 'audio/mpeg' }),
    captions: data.captions ?? null,
    translatedText: data.translatedText,
  }
}

export async function resolveFingerprint(fingerprint: string) {
  const response = await api.post('/fingerprint', { fingerprint })
  return response.data as { userId: number }
}

export type ThreadSummary = {
  conversationId: string
  displayName: string | null
  messageCount: number
  lastUserId: number
}

export async function getMessageThreads(messageId: string) {
  const response = await api.get(`/messages/${messageId}/threads`)
  return response.data as { threads: ThreadSummary[] }
}

export async function createThread(messageId: string, userId: number) {
  const response = await api.post(`/messages/${messageId}/threads`, { userId })
  return response.data as { conversationId: string; ownerPassword: string; url: string }
}

export async function getConversationThreads(conversationId: string) {
  const response = await api.get(`/conversations/${conversationId}/threads`)
  return response.data as { threads: ThreadSummary[] }
}

export async function createConversationThread(conversationId: string, userId: number) {
  const response = await api.post(`/conversations/${conversationId}/threads`, { userId })
  return response.data as { conversationId: string; ownerPassword: string; url: string }
}

export async function getConversationWiki(conversationId: string): Promise<string | null> {
  const response = await api.get<{ content: string | null }>(
    `/conversations/${conversationId}/wiki`,
    { headers: authHeaders(conversationId) },
  )
  return response.data.content
}
