import { query } from '../db.js'

export type GeneratedImageRecord = {
  id: string
  conversation_id: string
  message_id: string | null
  storage_namespace: string
  file_name: string
  image_title: string | null
  image_prompt: string | null
  user_prompt: string | null
  source_original_names: string[]
  source_size_bytes: string[] // BIGINT comes back as string from pg
}

/**
 * Persist a record for a freshly generated image. Returns the newly
 * allocated UUID so callers can feed it to the Chroma registration.
 */
export async function insertGeneratedImage(params: {
  conversationId: string
  messageId: string | null
  storageNamespace: string
  fileName: string
  imageTitle: string | null
  imagePrompt: string | null
  userPrompt: string | null
  sourceOriginalNames: string[]
  sourceSizeBytes: number[]
}): Promise<string> {
  const result = await query<{ id: string }>(
    `INSERT INTO generated_images
       (conversation_id, message_id, storage_namespace, file_name,
        image_title, image_prompt, user_prompt,
        source_original_names, source_size_bytes)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
     RETURNING id`,
    [
      params.conversationId,
      params.messageId,
      params.storageNamespace,
      params.fileName,
      params.imageTitle,
      params.imagePrompt,
      params.userPrompt,
      params.sourceOriginalNames,
      params.sourceSizeBytes,
    ],
  )
  return result.rows[0].id
}

export async function getGeneratedImageById(id: string) {
  const result = await query<GeneratedImageRecord>(
    `SELECT id, conversation_id, message_id, storage_namespace, file_name,
            image_title, image_prompt, user_prompt,
            source_original_names, source_size_bytes
       FROM generated_images
      WHERE id = $1`,
    [id],
  )
  return result.rows[0] || null
}
