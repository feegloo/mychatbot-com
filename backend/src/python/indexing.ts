import { config } from '../config.js'

export async function enrichMetadata(options: {
  filePaths: string[]
  exifMetadata?: Record<string, any>
  welcomeMessage?: string
}): Promise<Record<string, any>> {
  const response = await fetch(`${config.pythonServerUrl}/enrich-metadata`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      file_paths: options.filePaths,
      exif_metadata: options.exifMetadata || null,
      welcome_message: options.welcomeMessage || '',
    }),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Enrich-metadata error (${response.status}): ${text}`)
  }

  return response.json()
}

export async function indexConversation(options: {
  conversationId: string
  collectionName: string
  files: string[]
}) {
  const response = await fetch(`${config.pythonServerUrl}/index`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      conversation_id: options.conversationId,
      collection_name: options.collectionName,
      file_paths: options.files,
    }),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Python server error (${response.status}): ${text}`)
  }

  const parsedJson = await response.json()
  return {
    stdout: JSON.stringify(parsedJson),
    stderr: '',
    parsedJson,
    stdoutLogPath: '',
    stderrLogPath: '',
  }
}

export type IndexStreamEvent = {
  event: 'welcome_message' | 'page_progress' | 'complete' | 'error'
  data: Record<string, any>
}

/**
 * Streaming variant of indexConversation that yields NDJSON events
 * as the Python server processes the document:
 *   welcome_message → welcome text is ready
 *   complete        → indexing finished (chunks upserted, questions generated)
 */
export async function* indexConversationStream(options: {
  conversationId: string
  collectionName: string
  files: string[]
}): AsyncGenerator<IndexStreamEvent> {
  const response = await fetch(`${config.pythonServerUrl}/index-stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      conversation_id: options.conversationId,
      collection_name: options.collectionName,
      file_paths: options.files,
    }),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Python server error (${response.status}): ${text}`)
  }

  if (!response.body) {
    throw new Error('No response body from Python server')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const lines = buffer.split('\n')
    buffer = lines.pop()! // keep incomplete line in buffer

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed) continue // skip keepalive
      try {
        yield JSON.parse(trimmed) as IndexStreamEvent
      } catch {
        // skip malformed lines
      }
    }
  }

  // Process any remaining buffer
  if (buffer.trim()) {
    try {
      yield JSON.parse(buffer.trim()) as IndexStreamEvent
    } catch {
      // skip
    }
  }
}

export async function describeUrl(options: {
  url: string
  conversationId: string
  collectionName: string
}) {
  const response = await fetch(`${config.pythonServerUrl}/describe-url`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      url: options.url,
      conversation_id: options.conversationId,
      collection_name: options.collectionName,
    }),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Python server error (${response.status}): ${text}`)
  }

  const parsedJson = await response.json()
  return {
    stdout: JSON.stringify(parsedJson),
    stderr: '',
    parsedJson,
    stdoutLogPath: '',
    stderrLogPath: '',
  }
}
