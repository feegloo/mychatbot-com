export type ConversationLanguage = {
  code: string | null
  nativeName: string | null
}

const LANG_CODE_RE = /^[a-z]{2,3}(?:-[a-z]{2,4})?$/i

function normalizeLanguageCode(raw?: string | null): string | null {
  if (!raw) return null
  const trimmed = raw.trim()
  if (!trimmed || !LANG_CODE_RE.test(trimmed)) return null

  const [primary, region] = trimmed.split('-')
  if (!primary) return null
  if (!region) return primary.toLowerCase()
  return `${primary.toLowerCase()}-${region.toUpperCase()}`
}

function toSentenceCase(value: string): string {
  if (!value) return value
  const [first, ...rest] = value
  if (!first) return value
  return first.toLocaleUpperCase() + rest.join('')
}

function resolveNativeLanguageName(code: string): string {
  const primary = code.split('-')[0]
  if (!primary) return code

  try {
    const nativeName = new Intl.DisplayNames([primary], { type: 'language' }).of(primary)
    if (nativeName) return toSentenceCase(nativeName)
  } catch {
    // Fall through to English fallback.
  }

  try {
    const fallbackName = new Intl.DisplayNames(['en'], { type: 'language' }).of(primary)
    if (fallbackName) return toSentenceCase(fallbackName)
  } catch {
    // Fall through to code fallback.
  }

  return primary
}

export function resolveConversationLanguage(raw?: string | null): ConversationLanguage {
  const code = normalizeLanguageCode(raw)
  if (!code) {
    return { code: null, nativeName: null }
  }

  return {
    code,
    nativeName: resolveNativeLanguageName(code),
  }
}
