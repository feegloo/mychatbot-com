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
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { listMyConversations, type ConversationSummary } from '../api'
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

// Open an SSE connection per processing conversation instead of polling.
// When a conversation's indexing finishes (or errors), the backend emits
// `complete` / `error` on `/conversations/:id/events`; we refresh the list
// once to pick up the final status, displayName, and fileNames.
const sseConnections = new Map<string, EventSource>()

function apiBaseUrl(): string {
  return (import.meta.env.VITE_API_BASE_URL as string | undefined) || '/api'
}

function closeSSE(conversationId: string) {
  const es = sseConnections.get(conversationId)
  if (es) {
    es.close()
    sseConnections.delete(conversationId)
  }
}

function closeAllSSE() {
  for (const id of sseConnections.keys()) closeSSE(id)
}

function ensureSSEForProcessing() {
  const processingIds = new Set(
    conversations.value.filter((c) => c.status === 'processing').map((c) => c.conversationId),
  )
  // Close connections for conversations that are no longer processing
  for (const id of [...sseConnections.keys()]) {
    if (!processingIds.has(id)) closeSSE(id)
  }
  // Open connections for newly processing conversations
  for (const id of processingIds) {
    if (sseConnections.has(id)) continue
    const es = new EventSource(`${apiBaseUrl()}/conversations/${id}/events`)
    // The backend emits `complete` for any terminal state (ready or failed),
    // including catchup after auto-reconnects, so a single listener suffices.
    es.addEventListener('complete', () => {
      closeSSE(id)
      load()
    })
  }
}

async function load() {
  loading.value = true
  try {
    conversations.value = await listMyConversations()
    ensureSSEForProcessing()
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
  closeAllSSE()
  window.removeEventListener('conversation-updated', load)
})
</script>
