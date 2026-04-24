/**
 * Singleton global SSE connection that multiplexes real-time events for
 * multiple conversations over a single EventSource per app.
 *
 * Usage:
 *   const sseEvent = subscribeConversation(conversationId)   // in setup()
 *   watch(sseEvent, (evt) => { ... })                        // react to events
 *   unsubscribeConversation(conversationId)                  // in onUnmounted()
 *
 * The EventSource reconnects automatically whenever the subscription set
 * changes. EventSource also auto-reconnects on transport errors — no manual
 * retry logic is needed.
 *
 * Reconnects are debounced (80 ms) so rapid subscribe/unsubscribe calls
 * (e.g. ConversationNav loading a list) don't thrash the connection.
 */

import { onUnmounted, ref, type Ref } from 'vue'

export type SSEEvent = {
  event: string
  data: Record<string, unknown>
  /** Monotonic timestamp (Date.now()) so watchers can distinguish repeated same-event emissions. */
  ts: number
}

export function useSSE(conversationId: string): { sse: Ref<SSEEvent | null>; sss: Ref<SSEEvent | null> } {
  const sse = subscribeConversation(conversationId)

  // Unsubscribe only when component is actually unmounted (KeepAlive eviction),
  // not when temporarily deactivated.
  onUnmounted(() => {
    unsubscribeConversation(conversationId)
  })

  // `sss` alias keeps compatibility with earlier local naming in component code.
  return { sse, sss: sse }
}

/**
 * Registry helper for dynamic consumers (e.g. sidebar lists) that need to
 * attach/detach many conversation refs over time.
 */
export function useSSERegistry(): {
  getSSE: (conversationId: string) => Ref<SSEEvent | null>
  releaseSSE: (conversationId: string) => void
} {
  return {
    getSSE: (conversationId: string) => subscribeConversation(conversationId),
    releaseSSE: (conversationId: string) => unsubscribeConversation(conversationId),
  }
}

// ── Module-level singleton ──────────────────────────────────────────────────

/** Per-conversation reactive refs. Mutated by the global SSE handler. */
const refs = new Map<string, Ref<SSEEvent | null>>()
/** Set of conversation IDs currently included in the SSE subscription URL. */
const subscribed = new Set<string>()
let source: EventSource | null = null
let debounceTimer: ReturnType<typeof setTimeout> | null = null

function apiBase(): string {
  return (import.meta.env?.VITE_API_BASE_URL as string | undefined) || '/api'
}

function openConnection(): void {
  source?.close()
  source = null
  if (subscribed.size === 0) return

  const ids = [...subscribed].join(',')
  source = new EventSource(`${apiBase()}/events?ids=${encodeURIComponent(ids)}`)

  source.addEventListener('conversation_event', (e: MessageEvent) => {
    try {
      const { conversationId, event, data } = JSON.parse(e.data) as {
        conversationId: string
        event: string
        data: Record<string, unknown>
      }
      const r = refs.get(conversationId)
      if (r) r.value = { event, data, ts: Date.now() }
    } catch {
      // ignore malformed events
    }
  })
  // EventSource retries on its own — no additional error handling required.
}

function scheduleReopen(): void {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(openConnection, 80)
}

// ── Public API ──────────────────────────────────────────────────────────────

/**
 * Subscribe a conversation to the global SSE stream.
 * Returns a reactive ref that is set whenever an event arrives for this
 * conversation. The same ref is returned on repeated calls with the same ID.
 *
 * Call from component setup (outside lifecycle hooks) so the subscription
 * persists across KeepAlive deactivation cycles. Only call unsubscribeConversation
 * from onUnmounted (not onDeactivated) to keep updates flowing while cached.
 */
export function subscribeConversation(conversationId: string): Ref<SSEEvent | null> {
  if (!refs.has(conversationId)) {
    refs.set(conversationId, ref(null))
  }
  if (!subscribed.has(conversationId)) {
    subscribed.add(conversationId)
    scheduleReopen()
  }
  return refs.get(conversationId)!
}

/**
 * Remove a conversation from the global SSE stream.
 * Triggers a reconnect with the updated subscription list (debounced).
 */
export function unsubscribeConversation(conversationId: string): void {
  refs.delete(conversationId)
  if (subscribed.delete(conversationId)) {
    scheduleReopen()
  }
}
