/**
 * Per-message translation cache, persisted to localStorage.
 *
 * Keyed by `translation:{lang}:{messageId}` per the refactor spec. Values are
 * the translated content string. Storage is best-effort — any read/write error
 * (quota exceeded, private-mode, corrupted JSON) is silently ignored so the
 * in-memory cache in LanguageToggle still works as the source of truth.
 *
 * We intentionally do NOT key by source text because the same message may be
 * re-translated into multiple target languages over the conversation
 * lifetime, and messageId gives us a stable per-message identity that
 * survives reload. Messages without an id (streaming-in-flight) fall back to
 * the in-memory cache only.
 */

const KEY_PREFIX = 'translation:'

function buildKey(lang: string, messageId: string): string {
  return `${KEY_PREFIX}${lang}:${messageId}`
}

export function getStoredTranslation(lang: string, messageId: string): string | null {
  if (!lang || !messageId) return null
  try {
    return localStorage.getItem(buildKey(lang, messageId))
  } catch {
    return null
  }
}

export function setStoredTranslation(
  lang: string,
  messageId: string,
  translated: string,
): void {
  if (!lang || !messageId) return
  try {
    localStorage.setItem(buildKey(lang, messageId), translated)
  } catch {
    // Quota exceeded or storage disabled — skip persistence silently.
  }
}
