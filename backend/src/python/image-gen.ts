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
