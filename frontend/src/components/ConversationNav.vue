<template>
  <nav class="conv-nav" :class="{ collapsed: collapsed }" @click="onNavClick">
    <router-link to="/" class="conv-nav-new button" @click.stop="$emit('navigate')">
      <span class="conv-nav-new-icon">+</span>
      <span class="conv-nav-new-label">+ New chat</span>
    </router-link>

    <div class="conv-nav-list">
      <router-link
        v-for="conv in conversations"
        :key="conv.conversationId"
        :to="`/c/${conv.conversationId}`"
        class="conv-nav-item"
        :class="{ active: conv.conversationId === currentId }"
        @click="$emit('navigate')"
      >
        <span class="conv-nav-name">{{ convLabel(conv) }}</span>
        <span v-if="conv.status === 'processing'" class="conv-nav-dot processing"></span>
        <span v-else-if="conv.status === 'failed'" class="conv-nav-dot failed"></span>
      </router-link>

      <p v-if="!conversations.length && !loading" class="conv-nav-empty">No conversations yet</p>
    </div>

    <div class="conv-nav-collapsed-hint">
      <div
        v-for="conv in conversations.slice(0, 5)"
        :key="'mini-' + conv.conversationId"
        class="conv-nav-mini-item"
        :class="{ active: conv.conversationId === currentId }"
      ></div>
      <span v-if="conversations.length > 5" class="conv-nav-mini-more"
        >+{{ conversations.length - 5 }}</span
      >
    </div>

    <div class="conv-nav-bottom">
      <button
        class="conv-nav-collapse-btn"
        :aria-label="collapsed ? 'Expand menu' : 'Collapse menu'"
        @click.stop="
          $emit('toggle-collapse');
          $emit('navigate');
        "
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <polyline v-if="!collapsed" points="15 18 9 12 15 6" />
          <polyline v-else points="9 18 15 12 9 6" />
        </svg>
      </button>
      <DonateWidget />
      <svg
        class="conv-nav-expand-arrow"
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        @click.stop="$emit('toggle-collapse')"
      >
        <polyline points="9 18 15 12 9 6" />
      </svg>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, type WatchStopHandle } from 'vue'
import { useRoute } from 'vue-router'
import { listMyConversations, type ConversationSummary } from '../api'
import { useSSERegistry } from '../composables/useGlobalSSE'
import { cleanFileName } from '../utils/text'
import DonateWidget from './DonateWidget.vue'

const props = defineProps<{ collapsed: boolean }>()
const emit = defineEmits<{ navigate: []; 'toggle-collapse': [] }>()

function onNavClick(e: MouseEvent) {
  if (props.collapsed) {
    e.preventDefault()
    emit('toggle-collapse')
  }
}

function convLabel(conv: ConversationSummary): string {
  if (conv.displayName) return conv.displayName
  if (conv.fileNames?.length) {
    return conv.fileNames.map(cleanFileName).join(', ')
  }
  return `Conversation ${conv.conversationId.slice(0, 8)}…`
}

const route = useRoute()
const conversations = ref<ConversationSummary[]>([])
const loading = ref(false)
const currentId = ref('')
const { getSSE, releaseSSE } = useSSERegistry()

// Per-processing-conversation SSE watchers using the global multiplexed connection.
// Key: conversationId, Value: watcher stop handle
const processingWatchers = new Map<string, WatchStopHandle>()

function syncProcessingSSE() {
  const processingIds = new Set(
    conversations.value.filter((c) => c.status === 'processing').map((c) => c.conversationId),
  )
  // Stop watchers for conversations no longer in processing state
  for (const [id, stop] of processingWatchers) {
    if (!processingIds.has(id)) {
      stop()
      processingWatchers.delete(id)
      releaseSSE(id)
    }
  }
  // Start a watcher for each newly processing conversation
  for (const id of processingIds) {
    if (processingWatchers.has(id)) continue
    const sseRef = getSSE(id)
    const stop = watch(sseRef, (evt) => {
      if (!evt) return
      if (evt.event === 'complete' || evt.event === 'error') {
        const stopFn = processingWatchers.get(id)
        if (stopFn) {
          stopFn()
          processingWatchers.delete(id)
        }
        releaseSSE(id)
        load()
      }
    })
    processingWatchers.set(id, stop)
  }
}

async function load() {
  loading.value = true
  try {
    conversations.value = await listMyConversations()
    syncProcessingSSE()
  } catch {
    // silently fail – sidebar is non-critical
  } finally {
    loading.value = false
  }
}

watch(
  () => route.params.conversationId,
  (id) => {
    currentId.value = (id as string) || ''
  },
  { immediate: true },
)

// Reload list when navigating to a new conversation (e.g. after upload)
watch(
  () => route.path,
  () => load(),
)

onMounted(() => {
  load()
  window.addEventListener('conversation-updated', load)
})

onUnmounted(() => {
  for (const [id, stop] of processingWatchers) {
    stop()
    releaseSSE(id)
  }
  processingWatchers.clear()
  window.removeEventListener('conversation-updated', load)
})
</script>
