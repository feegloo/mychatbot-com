// ChatRAG Extension — Background Service Worker
// Handles all API calls and state management for the extension

const CHATRAG_API = 'https://chatrag.app/api'
const STORAGE_KEY = 'chatrag_state'
const POLL_INTERVAL_MS = 2500
const MAX_POLL_ATTEMPTS = 80 // ~3 minutes

// ── State helpers ─────────────────────────────────────────────────────────────

async function getState() {
  const result = await chrome.storage.local.get(STORAGE_KEY)
  return result[STORAGE_KEY] || {}
}

async function getUrlState(url) {
  const state = await getState()
  return state[url] || { status: 'idle' }
}

async function setUrlState(url, urlState) {
  const state = await getState()
  state[url] = { ...urlState, updatedAt: Date.now() }
  await chrome.storage.local.set({ [STORAGE_KEY]: state })
}

// ── Message handler ───────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'GET_URL_STATE') {
    getUrlState(message.url).then(sendResponse)
    return true
  }

  if (message.type === 'CREATE_CONVERSATION') {
    createConversationForUrl(message.url, message.tabId)
    sendResponse({ ok: true })
    return false
  }

  if (message.type === 'RESET_URL_STATE') {
    setUrlState(message.url, { status: 'idle' }).then(() => sendResponse({ ok: true }))
    return true
  }

  if (message.type === 'OPEN_WIDGET') {
    chrome.tabs
      .sendMessage(message.tabId, { type: 'OPEN_WIDGET', conversationId: message.conversationId })
      .catch(() => {})
    sendResponse({ ok: true })
    return false
  }

  return false
})

// ── Conversation creation flow ────────────────────────────────────────────────

async function createConversationForUrl(url, tabId) {
  // Prevent duplicate requests if already processing
  const current = await getUrlState(url)
  if (current.status === 'processing' || current.status === 'polling') return

  await setUrlState(url, { status: 'processing' })

  try {
    const response = await fetch(`${CHATRAG_API}/upload-url`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    })

    if (!response.ok) {
      const text = await response.text()
      throw new Error(`API error ${response.status}: ${text}`)
    }

    const data = await response.json()
    const { conversationId } = data

    if (!conversationId) throw new Error('No conversationId in response')

    await setUrlState(url, { status: 'polling', conversationId })
    await pollUntilReady(conversationId, url, tabId)
  } catch (err) {
    console.error('[ChatRAG] createConversationForUrl failed:', err.message)
    await setUrlState(url, { status: 'error', error: err.message })
  }
}

async function pollUntilReady(conversationId, url, tabId) {
  for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt++) {
    await delay(POLL_INTERVAL_MS)

    try {
      const response = await fetch(`${CHATRAG_API}/conversations/${conversationId}`)
      if (!response.ok) continue

      const data = await response.json()

      if (data.status === 'ready') {
        await setUrlState(url, { status: 'ready', conversationId })
        // Notify content script to show the widget
        notifyTab(tabId, { type: 'SHOW_WIDGET', conversationId })
        return
      }

      if (data.status === 'failed') {
        const errMsg = data.errorMessage || 'Processing failed'
        await setUrlState(url, { status: 'error', error: errMsg })
        return
      }
    } catch (pollErr) {
      console.warn('[ChatRAG] poll attempt failed:', pollErr.message)
    }
  }

  await setUrlState(url, { status: 'error', error: 'Timeout — page took too long to process' })
}

async function notifyTab(tabId, message) {
  try {
    await chrome.tabs.sendMessage(tabId, message)
  } catch {
    // Content script may not be ready; ignore — popup will handle showing the widget on next open
  }
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
