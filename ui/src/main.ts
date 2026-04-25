import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import * as Sentry from '@sentry/vue'
import './style.css'
import App from './App.vue'
import ConversationPage from './pages/ConversationPage.vue'

const router = createRouter({
  history: createWebHistory('/v2/'),
  routes: [
    { path: '/', component: App },
    { path: '/c/:uid', component: ConversationPage, props: true },
  ],
})

const sentryDsn = import.meta.env.VITE_SENTRY_DSN
if (sentryDsn) {
  Sentry.init({
    dsn: sentryDsn,
    integrations: [Sentry.browserTracingIntegration({ router })],
    tracesSampleRate: 1.0,
    tracePropagationTargets: ['localhost', 'chatrag.app', /^https:\/\/.+\.run\.app/],
  })
}

createApp(App).use(router).mount('#app')
