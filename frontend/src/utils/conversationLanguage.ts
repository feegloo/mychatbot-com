const CONV_LANG_KEY = 'conversation-languages'

export function getStoredConversationLanguage(conversationId?: string): string | null {
  if (!conversationId) return null
  try {
    const stored = localStorage.getItem(CONV_LANG_KEY)
    const map = stored ? JSON.parse(stored) : {}
    const lang = map[conversationId]
    return typeof lang === 'string' && lang.trim() ? lang : null
  } catch {
    return null
  }
}

export function storeConversationLanguage(
  conversationId: string | undefined,
  language: string,
  detectedLanguage?: string,
): void {
  if (!conversationId) return
  try {
    const stored = localStorage.getItem(CONV_LANG_KEY)
    const map = stored ? JSON.parse(stored) : {}
    if (detectedLanguage && language === detectedLanguage) {
      delete map[conversationId]
    } else {
      map[conversationId] = language
    }
    localStorage.setItem(CONV_LANG_KEY, JSON.stringify(map))
  } catch {
    // Ignore localStorage errors.
  }
}
