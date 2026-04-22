import { config } from '../config.js'

export async function generateVideo(options: {
  question: string
  storageDir: string
  welcomeMessages?: string[]
  collectionName?: string
  conversationId?: string
  chatHistory?: Array<{ role: string; content: string }>
  durationSeconds?: number
}) {
  const response = await fetch(`${config.pythonServerUrl}/generate-video`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question: options.question,
      storage_dir: options.storageDir,
      welcome_messages: options.welcomeMessages || [],
      collection_name: options.collectionName || '',
      conversation_id: options.conversationId || '',
      chat_history: options.chatHistory || [],
      duration_seconds: options.durationSeconds ?? null,
    }),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Python server error (${response.status}): ${text}`)
  }

  return (await response.json()) as {
    file_name: string
    duration_seconds: number
    video_prompt: string
    video_title: string
    rag_sources?: Array<{
      chunk_id: string
      text: string
      file_name: string
      section?: string | null
      page?: number | null
    }>
  }
}
