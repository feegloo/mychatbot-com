// ChatRAG Extension — Popup Script

const CHATRAG_BASE = 'https://chatrag.app'

// Step labels shown during processing
const PROCESSING_STEPS = [
  'Fetching page content…',
  'Analyzing content…',
  'Indexing for Q&A…',
  'Almost ready…',
]

let currentTab = null
let stepInterval = null
let stepIndex = 0

function el(id) { return document.getElementById(id) }

function showState(name) {
  ['initial', 'processing', 'ready', 'error'].forEach((s) => {
    el(`state-${s}`).classList.toggle('hidden', s !== name)
  })
}

function truncateUrl(url) {
  try {
    const u = new URL(url)
    const display = u.hostname + (u.pathname !== '/' ? u.pathname : '')
    return display.length > 42 ? display.slice(0, 42) + '…' : display
  } catch {
    return url.slice(0, 45)
  }
}

function startStepAnimation() {
  stepIndex = 0
  el('processing-step').textContent = PROCESSING_STEPS[0]
  stepInterval = setInterval(() => {
    stepIndex = (stepIndex + 1) % PROCESSING_STEPS.length
    el('processing-step').textContent = PROCESSING_STEPS[stepIndex]
  }, 6000)
}

function stopStepAnimation() {
  clearInterval(stepInterval)
  stepInterval = null
}

// ── Poll storage for state changes while popup is open ────────────────────────

let pollTimer = null

function startPolling(url) {
  stopPolling()
  pollTimer = setInterval(async () => {
    const state = await getUrlState(url)
    if (state.status === 'ready') {
      stopPolling()
      stopStepAnimation()
      renderReady(state.conversationId)
    } else if (state.status === 'error') {
      stopPolling()
      stopStepAnimation()
      renderError(state.error || 'Something went wrong')
    }
  }, 1000)
}

function stopPolling() {
  clearInterval(pollTimer)
  pollTimer = null
}

// ── Background messaging helpers ──────────────────────────────────────────────

function getUrlState(url) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ type: 'GET_URL_STATE', url }, resolve)
  })
}

function triggerCreate(url, tabId) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ type: 'CREATE_CONVERSATION', url, tabId }, resolve)
  })
}

function openWidget(tabId, conversationId) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ type: 'OPEN_WIDGET', tabId, conversationId }, resolve)
  })
}

function resetState(url) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ type: 'RESET_URL_STATE', url }, resolve)
  })
}

// ── Render helpers ────────────────────────────────────────────────────────────

function renderReady(conversationId) {
  showState('ready')

  el('btn-open-widget').onclick = async () => {
    await openWidget(currentTab.id, conversationId)
    window.close()
  }

  el('btn-open-tab').onclick = () => {
    chrome.tabs.create({ url: `${CHATRAG_BASE}/c/${conversationId}` })
    window.close()
  }

  el('btn-copy-embed').onclick = async () => {
    const snippet = `<script src="https://chatrag.app/embed.js" data-conversation="https://chatrag.app/c/${conversationId}"><\/script>`
    try {
      await navigator.clipboard.writeText(snippet)
    } catch {
      // Fallback for older browsers
      const ta = document.createElement('textarea')
      ta.value = snippet
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      ta.remove()
    }
    const label = el('btn-copy-embed-label')
    const btn = el('btn-copy-embed')
    label.textContent = 'Copied!'
    btn.classList.add('copied')
    setTimeout(() => {
      label.textContent = 'Embed on this site'
      btn.classList.remove('copied')
    }, 2000)
  }

  el('btn-new-chat').onclick = async () => {
    await resetState(currentTab.url)
    showState('initial')
  }
}

function renderError(message) {
  showState('error')
  el('error-text').textContent = message

  el('btn-retry').onclick = async () => {
    await resetState(currentTab.url)
    await triggerCreate(currentTab.url, currentTab.id)
    showState('processing')
    startStepAnimation()
    startPolling(currentTab.url)
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  currentTab = tab

  el('url-text').textContent = truncateUrl(tab.url)

  const state = await getUrlState(tab.url)

  if (state.status === 'ready') {
    renderReady(state.conversationId)
  } else if (state.status === 'processing' || state.status === 'polling') {
    showState('processing')
    startStepAnimation()
    startPolling(tab.url)
  } else if (state.status === 'error') {
    renderError(state.error || 'Something went wrong')
  } else {
    showState('initial')
  }

  el('btn-create').onclick = async () => {
    showState('processing')
    startStepAnimation()
    await triggerCreate(tab.url, tab.id)
    startPolling(tab.url)
  }
}

document.addEventListener('DOMContentLoaded', init)
