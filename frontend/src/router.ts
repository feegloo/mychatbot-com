import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import HomePage from './pages/HomePage.vue'
import ConversationPage from './pages/ConversationPage.vue'
import SharedMessagePage from './pages/SharedMessagePage.vue'
import DebugTablesPage from './pages/DebugTablesPage.vue'

const routes: RouteRecordRaw[] = [
  { path: '/', component: HomePage },
  { path: '/c/:conversationId', component: ConversationPage, props: true },
  { path: '/m/:messageId', component: SharedMessagePage, props: true },
  { path: '/debug', component: DebugTablesPage },
]

// Dev-only test harness routes used by the Playwright e2e suite. Excluded from
// production builds to avoid shipping fixtures to real users.
if (import.meta.env.DEV) {
  routes.push({
    path: '/__test__/mermaid',
    component: () => import('./pages/MermaidTestPage.vue'),
  })
}

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Keep canonical / OG / Twitter URL meta tags in sync with the current route
// so that iOS Safari's native share sheet copies the actual page URL instead
// of the hardcoded root from index.html.
router.afterEach((to) => {
  if (to.path === '/') {
    document.title = 'chatrag.app'
  }

  const url = window.location.href

  const canonical = document.querySelector<HTMLLinkElement>('link[rel="canonical"]')
  if (canonical) canonical.href = url

  const ogUrl = document.querySelector<HTMLMetaElement>('meta[property="og:url"]')
  if (ogUrl) ogUrl.content = url

  const twitterUrl = document.querySelector<HTMLMetaElement>('meta[property="twitter:url"]')
  if (twitterUrl) twitterUrl.content = url
})

export default router
