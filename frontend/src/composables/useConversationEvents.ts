import { ref, type Ref } from 'vue'

export type ProcessingStep = 'generating_welcome' | 'indexing_pages' | ''

const STEP_LABELS: Record<ProcessingStep, string> = {
  generating_welcome: 'Processing',
  indexing_pages: 'Indexing pages for Q&A…',
  '': '',
}

export function stepLabel(step: ProcessingStep): string {
  return STEP_LABELS[step] || ''
}

/**
 * Connects to the backend SSE endpoint for a conversation and
 * exposes reactive flags for welcome message arrival and indexing completion.
 *
 * Events from server:
 *   welcome_message — the welcome message has been saved to DB
 *   complete        — indexing finished, conversation is ready
 *   page_progress   — live parsing progress: { parsed, total }
 *   error           — fatal error during indexing
 */
export function useConversationEvents(conversationId: string) {
  const welcomeReceived = ref(false)
  const indexingComplete = ref(false)
  const processingStep: Ref<ProcessingStep> = ref('generating_welcome')
  const parsedPages = ref(0)
  const totalPages = ref(0)

  let eventSource: EventSource | null = null
  let onWelcomeCb: (() => void) | null = null
  let onCompleteCb: (() => void) | null = null

  function onWelcome(cb: () => void) {
    onWelcomeCb = cb
  }

  function onComplete(cb: () => void) {
    onCompleteCb = cb
  }

  function connect() {
    const baseUrl = import.meta.env?.VITE_API_BASE_URL || '/api'
    eventSource = new EventSource(`${baseUrl}/conversations/${conversationId}/events`)

    eventSource.addEventListener('welcome_message', () => {
      if (welcomeReceived.value) return
      welcomeReceived.value = true
      processingStep.value = 'indexing_pages'
      onWelcomeCb?.()
    })

    eventSource.addEventListener('page_progress', (e: MessageEvent) => {
      try {
        const { parsed, total } = JSON.parse(e.data)
        parsedPages.value = parsed
        totalPages.value = total
      } catch {
        // ignore malformed events
      }
    })

    eventSource.addEventListener('complete', () => {
      indexingComplete.value = true
      processingStep.value = ''
      onCompleteCb?.()
      disconnect()
    })

    eventSource.addEventListener('error', () => {
      // EventSource auto-reconnects on transient errors.
      // If the conversation has already completed, the server sends
      // catchup events and closes — no action needed here.
    })
  }

  function disconnect() {
    eventSource?.close()
    eventSource = null
  }

  return {
    welcomeReceived,
    indexingComplete,
    processingStep,
    parsedPages,
    totalPages,
    onWelcome,
    onComplete,
    connect,
    disconnect,
  }
}
