const FINGERPRINT_KEY = 'chatrag-fingerprint'
const USER_ID_KEY = 'chatrag-user-id'

let cachedFingerprint: string | null = null
let cachedUserId: number | null = null

export async function getBrowserFingerprint(): Promise<string> {
  if (cachedFingerprint) return cachedFingerprint

  // Check localStorage first
  const stored = localStorage.getItem(FINGERPRINT_KEY)
  if (stored) {
    cachedFingerprint = stored
    return stored
  }

  const FingerprintJS = (await import('@fingerprintjs/fingerprintjs')).default
  const fp = await FingerprintJS.load()
  const result = await fp.get()
  cachedFingerprint = result.visitorId
  localStorage.setItem(FINGERPRINT_KEY, cachedFingerprint)
  return cachedFingerprint
}

export function getUserId(): number | null {
  if (cachedUserId !== null) return cachedUserId
  const stored = localStorage.getItem(USER_ID_KEY)
  if (stored) {
    cachedUserId = parseInt(stored, 10)
    return cachedUserId
  }
  return null
}

export function setUserId(userId: number) {
  cachedUserId = userId
  localStorage.setItem(USER_ID_KEY, String(userId))
}
