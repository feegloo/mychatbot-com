import type { ConversationMessageRecord } from '../types.js'

/**
 * Build full chat history from conversation messages.
 * Includes all user+assistant exchanges (excluding welcome messages)
 * with timestamps for contextual continuity.
 */
export function buildChatHistory(
  messages: ConversationMessageRecord[],
): { role: string; content: string; timestamp?: string }[] {
  return messages
    .filter((msg) => {
      // Skip welcome/upload messages (assistant messages with _uploadedFileNames)
      if (msg.role === 'assistant' && msg.citations_json?._uploadedFileNames) return false
      return true
    })
    .map((msg) => ({
      role: msg.role,
      content: msg.content,
      ...(msg.created_at ? { timestamp: msg.created_at } : {}),
    }))
}

/**
 * Find ALL welcome/upload messages (assistant messages with _uploadedFileNames in citations).
 * Returns them in chronological order (oldest first) so the prompt sees uploads in time order.
 */
export function getWelcomeMessages(messages: ConversationMessageRecord[]): string[] {
  return messages
    .filter((msg) => msg.role === 'assistant' && msg.citations_json?._uploadedFileNames)
    .map((msg) => msg.content)
}
