import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import HomePage from './pages/HomePage.vue'
import ConversationPage from './pages/ConversationPage.vue'
import SharedMessagePage from './pages/SharedMessagePage.vue'
import DebugTablesPage from './pages/DebugTablesPage.vue'
import EmbedPage from './pages/EmbedPage.vue'

const routes: RouteRecordRaw[] = [
  { path: '/', component: HomePage },
  { path: '/c/:conversationId', component: ConversationPage, props: true },
  { path: '/m/:messageId', component: SharedMessagePage, props: true },
  { path: '/embed/:conversationId', component: EmbedPage, props: true, meta: { embed: true } },
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

export default createRouter({
  history: createWebHistory(),
  routes,
})
