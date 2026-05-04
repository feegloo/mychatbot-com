import { ConversationLanguagesTable } from './database'

export async function getStoredConversationLanguage(
  conversationId?: string,
): Promise<string | null> {
  if (!conversationId) return null
  try {
    return await ConversationLanguagesTable.get(conversationId)
  } catch {
    return null
  }
}

export async function storeConversationLanguage(
  conversationId: string | undefined,
  language: string,
  detectedLanguage?: string,
): Promise<void> {
  if (!conversationId) return
  try {
    if (detectedLanguage && language === detectedLanguage) {
      await ConversationLanguagesTable.remove(conversationId)
    } else {
      await ConversationLanguagesTable.set(conversationId, language)
    }
  } catch {
    // Ignore storage errors.
  }
}
