import { config } from '../config.js'

type ImageQuality = 'auto' | 'high' | 'low'

export async function generateImage(options: {
  question: string
  storageDir: string
  context?: string
  welcomeMessages?: string[]
  collectionName?: string
  conversationId?: string
  chatHistory?: Array<{ role: string; content: string }>
  size?: string
  quality?: ImageQuality
  referenceImagePaths?: string[]
}) {
  const response = await fetch(`${config.pythonServerUrl}/generate-image`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question: options.question,
      storage_dir: options.storageDir,
      context: options.context || '',
      welcome_messages: options.welcomeMessages || [],
      collection_name: options.collectionName || '',
      conversation_id: options.conversationId || '',
      chat_history: options.chatHistory || [],
      size: options.size || '1024x1024',
      quality: options.quality || 'low',
      reference_image_paths: options.referenceImagePaths || [],
    }),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Python server error (${response.status}): ${text}`)
  }

  return (await response.json()) as {
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
}

export async function announceImage(options: {
  question: string
  welcomeMessages?: string[]
  chatHistory?: Array<{ role: string; content: string }>
}): Promise<{ announcement: string }> {
  const response = await fetch(`${config.pythonServerUrl}/announce-image`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question: options.question,
      welcome_messages: options.welcomeMessages || [],
      chat_history: options.chatHistory || [],
    }),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Python server error (${response.status}): ${text}`)
  }

  return (await response.json()) as { announcement: string }
}

export type ImageStreamEvent =
  | { event: 'prompt_ready'; data: { image_prompt: string; image_title: string } }
  | { event: 'partial'; data: { b64: string; index: number } }
  | {
      event: 'complete'
      data: {
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
    }
  | { event: 'error'; data: { error: string } }

/**
 * Streams NDJSON events from the Python `/generate-image-stream` endpoint.
 * Each yielded line is one JSON event; callers should parse and dispatch.
 * Keepalive blank lines are filtered out.
 */
export async function* generateImageStream(options: {
  question: string
  storageDir: string
  welcomeMessages?: string[]
  collectionName?: string
  conversationId?: string
  chatHistory?: Array<{ role: string; content: string }>
  size?: string
  quality?: ImageQuality
  referenceImagePaths?: string[]
  signal?: AbortSignal
}): AsyncGenerator<ImageStreamEvent, void, void> {
  const response = await fetch(`${config.pythonServerUrl}/generate-image-stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal: options.signal,
    body: JSON.stringify({
      question: options.question,
      storage_dir: options.storageDir,
      welcome_messages: options.welcomeMessages || [],
      collection_name: options.collectionName || '',
      conversation_id: options.conversationId || '',
      chat_history: options.chatHistory || [],
      size: options.size || '1024x1024',
      quality: options.quality || 'low',
      reference_image_paths: options.referenceImagePaths || [],
    }),
  })

  if (!response.ok || !response.body) {
    const text = await response.text().catch(() => '')
    throw new Error(`Python server error (${response.status}): ${text}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let nl = buffer.indexOf('\n')
    while (nl !== -1) {
      const line = buffer.slice(0, nl).trim()
      buffer = buffer.slice(nl + 1)
      nl = buffer.indexOf('\n')
      if (!line) continue
      try {
        yield JSON.parse(line) as ImageStreamEvent
      } catch {
        // Ignore keepalive / malformed lines — the final 'complete' or 'error'
        // event carries the outcome the caller needs.
      }
    }
  }
}
