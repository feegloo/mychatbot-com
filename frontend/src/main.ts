import { createApp } from 'vue'
import FloatingVue from 'floating-vue'

console.log(__COMMIT_HASH__)
import 'floating-vue/dist/style.css'
import * as Sentry from '@sentry/vue'
import App from './App.vue'
import router from './router'
import './style.css'
import { initDatabase } from './utils/database'
import { migrateLocalStorageToIndexedDB } from './utils/migration'
import { initTokensCache, saveConversationToken } from './api'
import { initFingerprintCache } from './utils/fingerprint'
import { initHomeLang } from './i18n/homeLocale'
import { decodeConversationTokens, CONVERSATIONS_PARAM } from './utils/conversationLink'

const app = createApp(App)

// After a new deployment, hashed chunk filenames change. If the browser has a
// stale main bundle that references old chunk URLs, dynamic imports will fail
// with a "Failed to fetch dynamically imported module" TypeError. Reload once
// to pick up the fresh index.html and updated asset URLs.
window.addEventListener('unhandledrejection', (event: PromiseRejectionEvent) => {
  const isChunkLoadError =
    event.reason instanceof TypeError &&
    event.reason.message.includes('Failed to fetch dynamically imported module')
  if (isChunkLoadError) {
    const key = 'chunk-reload'
    if (!sessionStorage.getItem(key)) {
      sessionStorage.setItem(key, '1')
      window.location.reload()
    }
  }
})

Sentry.init({
  app,
  dsn: import.meta.env.VITE_SENTRY_DSN,
  environment: import.meta.env.MODE === 'production' ? 'prod' : 'dev',
  integrations: [Sentry.browserTracingIntegration({ router })],
  sendDefaultPii: true,
  tracesSampleRate: 1.0,
  replaysSessionSampleRate: 0,
  replaysOnErrorSampleRate: 1.0,
  enableLogs: true,
  beforeSendLog: (log) => {
    if (import.meta.env.MODE === 'production' && log.level === 'debug') {
      return null
    }
    return log
  },
})

// Lazy-load the replay integration — only captures sessions with errors
Sentry.lazyLoadIntegration('replayIntegration').then((replay) => {
  Sentry.addIntegration(
    replay({
      maskAllText: false,
      blockAllMedia: false,
      networkDetailAllowUrls: [window.location.origin],
    }),
  )
})

FloatingVue.options.themes['more-questions'] = {
  $extend: 'dropdown',
  placement: 'top-start',
}

/**
 * If the page was opened with a ?conversations=<encoded> query param, decode
 * the token bundle, persist each entry to IndexedDB (via saveConversationToken),
 * and then strip the param from the URL so it doesn't linger in the address bar
 * or get accidentally shared again.
 */
function importConversationsFromUrl(): void {
  const params = new URLSearchParams(window.location.search)
  const encoded = params.get(CONVERSATIONS_PARAM)
  if (!encoded) return

  const entries = decodeConversationTokens(encoded)
  if (entries && entries.length > 0) {
    for (const { conversationId, token } of entries) {
      saveConversationToken(conversationId, token)
    }
  } else {
    console.warn('[chatrag] ?conversations= param present but could not be decoded')
  }

  // Clean up: remove the param so it's not visible to the user or bookmarked.
  params.delete(CONVERSATIONS_PARAM)
  const newSearch = params.toString()
  const newUrl = window.location.pathname + (newSearch ? `?${newSearch}` : '') + window.location.hash
  window.history.replaceState(null, '', newUrl)
}

// Initialize IndexedDB, run one-time LS migration, populate in-memory caches,
// then mount the app. All synchronous LS reads have been replaced by these
// cache-backed equivalents — the app only mounts once caches are ready.
async function bootstrap() {
  initDatabase()
  await migrateLocalStorageToIndexedDB()
  await Promise.all([initTokensCache(), initFingerprintCache(), initHomeLang()])

  // Import shared conversations from ?conversations= URL param (shareable link).
  // Must run after initTokensCache() so saveConversationToken writes into a
  // fully-initialised cache before the sidebar loads.
  importConversationsFromUrl()
  app.use(router).use(FloatingVue)

  // floating-vue 5.2.2: the v-tooltip directive hook destructures its second
  // argument as `{ value, modifiers }` and throws when it receives `undefined`.
  // This can happen during rapid reactive updates (e.g. bulk translation from
  // IndexedDB). Patch the hook to silently skip undefined bindings.
  type DirectiveLike = { beforeMount?: (el: Element, binding: unknown) => void; updated?: (el: Element, binding: unknown) => void }
  const dirCtx = (app as { _context?: { directives?: Record<string, DirectiveLike> } })._context?.directives
  const origTooltip = dirCtx?.tooltip
  if (origTooltip?.beforeMount && origTooltip?.updated) {
    const safe =
      (fn: (el: Element, binding: unknown) => void) =>
      (el: Element, binding: unknown) => {
        if (binding != null) fn(el, binding)
      }
    app.directive('tooltip', { ...origTooltip, beforeMount: safe(origTooltip.beforeMount), updated: safe(origTooltip.updated) })
  }

  app.mount('#app')
}

void bootstrap()
