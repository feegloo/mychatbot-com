import { ConfigurationsTable } from './database'

const FINGERPRINT_KEY = 'chatrag-fingerprint'
const USER_ID_KEY = 'chatrag-user-id'

let cachedFingerprint: string | null = null
let cachedUserId: number | null = null

// Deduplicates concurrent calls: at most one POST /fingerprint in-flight at a time.
let userIdResolutionPromise: Promise<number> | null = null

/** Load fingerprint and userId from IndexedDB into in-memory cache. Call once at app startup. */
export async function initFingerprintCache(): Promise<void> {
  const [fp, uid] = await Promise.all([
    ConfigurationsTable.get<string>(FINGERPRINT_KEY),
    ConfigurationsTable.get<string>(USER_ID_KEY),
  ])
  if (fp) cachedFingerprint = fp
  if (uid) cachedUserId = parseInt(uid, 10)
}

export async function getBrowserFingerprint(): Promise<string> {
  if (cachedFingerprint) return cachedFingerprint

  const FingerprintJS = (await import('@fingerprintjs/fingerprintjs')).default
  const fp = await FingerprintJS.load()
  const result = await fp.get()
  cachedFingerprint = result.visitorId
  await ConfigurationsTable.set(FINGERPRINT_KEY, cachedFingerprint)
  return cachedFingerprint
}

export function getUserId(): number | null {
  return cachedUserId
}

export async function setUserId(userId: number): Promise<void> {
  cachedUserId = userId
  await ConfigurationsTable.set(USER_ID_KEY, String(userId))
}

/**
 * Lazily resolves the browser fingerprint to a server-side userId.
 * Multiple concurrent callers share the same in-flight request.
 * Used only where the frontend needs to know its own userId (e.g. "YOU" display).
 */
export async function ensureUserId(): Promise<number> {
  if (cachedUserId !== null) return cachedUserId
  if (!userIdResolutionPromise) {
    userIdResolutionPromise = (async () => {
      const { resolveFingerprint } = await import('../api')
      const fingerprint = await getBrowserFingerprint()
      const { userId } = await resolveFingerprint(fingerprint)
      await setUserId(userId)
      return userId
    })().finally(() => {
      // Allow a retry if the promise rejects.
      userIdResolutionPromise = null
    })
  }
  return userIdResolutionPromise
}
