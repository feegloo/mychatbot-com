<template>
  <div class="app-layout" :class="{ 'sidebar-collapsed': sidebarCollapsed, 'embed-mode': isEmbed, 'sidebar-no-transition': sidebarNoTransition }">
    <template v-if="!isEmbed">
      <div class="sidebar-overlay" :class="{ open: sidebarOpen }" @click="sidebarOpen = false"></div>
      <ConversationNav
        :class="{ open: sidebarOpen }"
        :collapsed="sidebarCollapsed"
        @navigate="sidebarOpen = false"
        @toggle-collapse="sidebarCollapsed = !sidebarCollapsed"
      />
    </template>
    <main class="app-main">
      <button v-if="!isEmbed" class="sidebar-toggle" aria-label="Toggle menu" @click="sidebarOpen = !sidebarOpen">
        <svg
          width="22"
          height="22"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
        >
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>
      <router-view v-slot="{ Component }">
        <KeepAlive :include="['ConversationPage']" :max="5">
          <component :is="Component" :key="$route.fullPath" />
        </KeepAlive>
      </router-view>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import ConversationNav from './components/ConversationNav.vue'
import { getBrowserFingerprint, getUserId, setUserId } from './utils/fingerprint'
import { resolveFingerprint } from './api'
import { ConfigurationsTable } from './utils/database'

const sidebarOpen = ref(false)
const sidebarCollapsed = ref(false)
const sidebarNoTransition = ref(true)
const isEmbed = computed(() => route.query.embed === '1')

watch(sidebarCollapsed, (v) => void ConfigurationsTable.set('sidebarCollapsed', String(v)))
const route = useRoute()

watch(
  () => route.path,
  () => {
    sidebarOpen.value = false
  },
)

// Initialize fingerprint and resolve userId on app start
onMounted(async () => {
  // Restore sidebar state from IndexedDB (it was loaded into configs cache at startup)
  const stored = await ConfigurationsTable.get<string>('sidebarCollapsed')
  if (stored === 'true') sidebarCollapsed.value = true
  // Allow one rAF so the DOM reflects the initial state before enabling transitions
  requestAnimationFrame(() => { sidebarNoTransition.value = false })

  try {
    if (getUserId() !== null) return // already resolved
    const fingerprint = await getBrowserFingerprint()
    const { userId } = await resolveFingerprint(fingerprint)
    await setUserId(userId)
  } catch (err) {
    console.error('[fingerprint init]', err)
  }
})
</script>
