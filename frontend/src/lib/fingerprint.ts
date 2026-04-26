const STORAGE_KEY = "chatrag_fingerprint"

/**
 * Returns persistent anonymous browser fingerprint stored in Local Storage.
 */
export function getOrCreateFingerprint(): string {
    const existing = localStorage.getItem(STORAGE_KEY)

    if (existing) {
        return existing
    }

    const fingerprint = crypto.randomUUID()
    localStorage.setItem(STORAGE_KEY, fingerprint)
    return fingerprint
}

/**
 * Creates unique trace id propagated through HTTP, Pub/Sub, DB, worker, and Sentry.
 */
export function createTraceId(): string {
    return crypto.randomUUID()
}
