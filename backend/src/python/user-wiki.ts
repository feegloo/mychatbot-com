/**
 * Thin TypeScript client for the Python /user-wiki endpoint.
 *
 * Calls the Python server to synthesise a master cross-conversation wiki for
 * a user from their per-conversation "idea files" (Section-3a wikis).
 */

import { config } from '../config.js'

export async function buildUserWikiViaApi(options: {
  userId: number
  conversationWikis: { conversationId: string; content: string }[]
}): Promise<string> {
  const response = await fetch(`${config.pythonServerUrl}/user-wiki`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: options.userId,
      conversation_wikis: options.conversationWikis.map((w) => ({
        conversation_id: w.conversationId,
        content: w.content,
      })),
    }),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Python /user-wiki error (${response.status}): ${text}`)
  }

  const data = (await response.json()) as { content?: string }
  if (!data.content) {
    throw new Error('Python /user-wiki returned empty content')
  }
  return data.content
}
