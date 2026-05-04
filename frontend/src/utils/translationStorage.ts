/**
 * Per-message translation cache, persisted to IndexedDB (translations table).
 *
 * Keyed by lang + messageId. Values are the translated content string.
 * Storage is best-effort — any error is silently ignored so the in-memory
 * cache in LanguageToggle still works as the source of truth.
 *
 * Messages without an id (streaming-in-flight) fall back to the in-memory
 * cache only.
 */
import { TranslationsTable } from './database'

export async function getStoredTranslation(
  lang: string,
  messageId: string,
): Promise<string | null> {
  if (!lang || !messageId) return null
  try {
    return await TranslationsTable.get(lang, messageId)
  } catch {
    return null
  }
}

export async function setStoredTranslation(
  lang: string,
  messageId: string,
  translated: string,
): Promise<void> {
  if (!lang || !messageId) return
  try {
    await TranslationsTable.set(lang, messageId, translated)
  } catch {
    // Quota exceeded or storage disabled — skip persistence silently.
  }
}

/**
 * Bulk-fetch cached translations for a list of messages.
 * Returns a Map of messageId → translated text for all cached entries.
 */
export async function getBulkStoredTranslations(
  lang: string,
  messageIds: string[],
): Promise<Map<string, string>> {
  if (!lang || !messageIds.length) return new Map()
  try {
    return await TranslationsTable.getBulk(lang, messageIds)
  } catch {
    return new Map()
  }
}
