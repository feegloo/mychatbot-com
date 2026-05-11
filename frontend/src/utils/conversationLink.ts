/**
 * Encode / decode a bundle of conversation tokens for sharing via a URL parameter.
 *
 * Encoding pipeline:
 *   Array<{conversationId, token}>
 *     → JSON.stringify
 *     → UTF-8 bytes (TextEncoder)
 *     → base64url (URL-safe, no padding)
 *
 * The resulting string is safe to embed directly in a query-string value.
 */

export type ConversationTokenEntry = {
  conversationId: string
  token: string
}

/** URL query-param name used by the shareable-link feature. */
export const CONVERSATIONS_PARAM = 'conversations'

/**
 * Encode an array of {conversationId, token} pairs into a compact URL-safe string.
 * Uses base64url (RFC 4648 §5) — no padding characters.
 */
export function encodeConversationTokens(entries: ConversationTokenEntry[]): string {
  const json = JSON.stringify(entries)
  // Convert the UTF-8 string to bytes, then to a base64url string.
  const bytes = new TextEncoder().encode(json)
  // Build a binary string from the byte array so btoa() can consume it.
  let binary = ''
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  // base64 → base64url: replace + with -, / with _, strip padding =
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '')
}

/**
 * Decode a base64url-encoded string back into conversation token pairs.
 * Returns null if the string is malformed or the decoded data is invalid.
 */
export function decodeConversationTokens(encoded: string): ConversationTokenEntry[] | null {
  try {
    // Restore standard base64 padding.
    const padded = encoded.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((encoded.length % 4) || 4)
    const binary = atob(padded)
    const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0))
    const json = new TextDecoder().decode(bytes)
    const parsed: unknown = JSON.parse(json)

    if (!isValidTokenArray(parsed)) return null
    return parsed
  } catch {
    return null
  }
}

function isValidTokenArray(value: unknown): value is ConversationTokenEntry[] {
  if (!Array.isArray(value)) return false
  return value.every(
    (item) =>
      item !== null &&
      typeof item === 'object' &&
      typeof (item as Record<string, unknown>).conversationId === 'string' &&
      typeof (item as Record<string, unknown>).token === 'string',
  )
}

/**
 * Build a full shareable URL for the given entries.
 * Defaults to the current origin when called in a browser context.
 */
export function buildConversationsLink(
  entries: ConversationTokenEntry[],
  baseUrl = typeof window !== 'undefined' ? window.location.origin : 'https://chatrag.app',
): string {
  const param = encodeConversationTokens(entries)
  // Strip trailing slash so the param starts immediately after the origin.
  const origin = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl
  return `${origin}?${CONVERSATIONS_PARAM}=${param}`
}
