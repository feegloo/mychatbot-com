import axios, { AxiosError } from 'axios'

const api = axios.create({
  // @ts-ignore
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
})

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
  suggestedQuestions?: string[]
  userId?: number
  threadReplyCount?: number
  isParentMessage?: boolean
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
  suggestedQuestions: string[]
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

export async function askQuestion(conversationId: string, question: string, userId?: number) {
  const response = await api.post(
    '/ask',
    { conversationId, question, ...(userId ? { userId } : {}) },
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

export async function generateImage(conversationId: string, question: string, userId?: number) {
  const response = await api.post(
    '/generate-image',
    { conversationId, question, ...(userId ? { userId } : {}) },
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

function getBaseUrl() {
  // @ts-ignore
  return (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/api$/, '')
}

export function getStorageUrl(conversationId: string, fileName: string) {
  return `${getBaseUrl()}/api/storage/${conversationId}/${encodeURIComponent(fileName)}`
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

export async function getDebugTables(username: string, password: string, offset = 0) {
  const response = await api.get('/debug/tables', {
    auth: { username, password },
    params: { offset },
  })
  return response.data as {
    conversations: Record<string, unknown>[]
    conversation_messages: Record<string, unknown>[]
    suggested_questions: Record<string, unknown>[]
    uploaded_files: Record<string, unknown>[]
    user_fingerprints: Record<string, unknown>[]
    conversation_access_tokens: Record<string, unknown>[]
    access_requests: Record<string, unknown>[]
    users: Record<string, unknown>[]
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
