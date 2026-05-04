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
import { initTokensCache } from './api'
import { initFingerprintCache } from './utils/fingerprint'
import { initHomeLang } from './i18n/homeLocale'

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

// Initialize IndexedDB, run one-time LS migration, populate in-memory caches,
// then mount the app. All synchronous LS reads have been replaced by these
// cache-backed equivalents — the app only mounts once caches are ready.
async function bootstrap() {
  initDatabase()
  await migrateLocalStorageToIndexedDB()
  await Promise.all([initTokensCache(), initFingerprintCache(), initHomeLang()])
  app.use(router).use(FloatingVue).mount('#app')
}

void bootstrap()
