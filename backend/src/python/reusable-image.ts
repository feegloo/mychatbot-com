import { config } from '../config.js'
import logger from '../logger.js'

export type ReusableImageMatch = {
  image_id: string
  distance: number
  conversation_id: string
  storage_namespace: string
  file_name: string
  image_title: string
  image_prompt: string
  source_original_names: string[]
}

/**
 * POST the image description/embedding into the Python-side Chroma
 * collection that backs cross-conversation reuse. Failures are soft — the
 * caller should keep going; the image is still persisted in Postgres and
 * only the "findable by future chats" side effect is lost.
 */
export async function registerReusableImage(payload: {
  imageId: string
  conversationId: string
  storageNamespace: string
  fileName: string
  imageTitle?: string | null
  imagePrompt?: string | null
  userPrompt?: string | null
  sourceOriginalNames: string[]
}): Promise<void> {
  try {
    const response = await fetch(`${config.pythonServerUrl}/register-image`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_id: payload.imageId,
        conversation_id: payload.conversationId,
        storage_namespace: payload.storageNamespace,
        file_name: payload.fileName,
        image_title: payload.imageTitle ?? null,
        image_prompt: payload.imagePrompt ?? null,
        user_prompt: payload.userPrompt ?? null,
        source_original_names: payload.sourceOriginalNames,
      }),
    })
    if (!response.ok) {
      const text = await response.text()
      logger.warn({ status: response.status, text }, 'register-image non-ok')
    }
  } catch (err) {
    logger.warn({ err, imageId: payload.imageId }, 'register-image request failed')
  }
}

export async function findReusableImage(payload: {
  queryText: string
  excludeConversationId?: string
  preferredSourceFiles?: string[]
  maxDistance?: number
}): Promise<ReusableImageMatch | null> {
  try {
    const response = await fetch(`${config.pythonServerUrl}/reusable-image`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query_text: payload.queryText,
        exclude_conversation_id: payload.excludeConversationId ?? null,
        preferred_source_files: payload.preferredSourceFiles ?? null,
        max_distance: payload.maxDistance ?? null,
      }),
    })
    if (!response.ok) {
      const text = await response.text()
      logger.warn({ status: response.status, text }, 'reusable-image non-ok')
      return null
    }
    const body = (await response.json()) as { match: ReusableImageMatch | null }
    return body.match
  } catch (err) {
    logger.warn({ err }, 'reusable-image request failed')
    return null
  }
}
