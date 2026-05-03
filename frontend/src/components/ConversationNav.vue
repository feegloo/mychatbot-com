<template>
  <nav class="conv-nav" :class="{ collapsed: collapsed }" @click="onNavClick">
    <router-link to="/" class="conv-nav-new button" @click.stop="$emit('navigate')">
      <span class="conv-nav-new-icon">+</span>
      <span class="conv-nav-new-label">+ New chat</span>
    </router-link>

    <div class="conv-nav-list">
      <router-link
        v-for="conv in visibleConversations"
        :key="conv.conversationId"
        :to="conversationRoute(conv)"
        class="conv-nav-item"
        :class="{
          active: conv.conversationId === currentId,
          'search-match': searchHitByConversationId.has(conv.conversationId),
        }"
        @click="$emit('navigate')"
      >
        <span class="conv-nav-name">{{ convLabel(conv) }}</span>
        <span
          v-if="searchHitByConversationId.has(conv.conversationId)"
          class="conv-nav-search-count"
          :title="`${searchHitByConversationId.get(conv.conversationId)?.matchCount || 0} matches`"
        >
          {{ searchHitByConversationId.get(conv.conversationId)?.matchCount }}
        </span>
        <span v-if="conv.isLocal" class="conv-nav-local-icon" title="Local / offline conversation">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M17.5 19H9a7 7 0 01-2.12-13.66"/>
            <path d="M22 16.74A10 10 0 0012.06 3"/>
            <line x1="2" y1="2" x2="22" y2="22"/>
          </svg>
        </span>
        <span v-if="conv.status === 'processing'" class="conv-nav-dot processing"></span>
        <span v-else-if="conv.status === 'failed'" class="conv-nav-dot failed"></span>
      </router-link>

      <p v-if="searchOpen && searchInputTrimmed.length > 0 && searchInputTrimmed.length < 4" class="conv-nav-empty">
        Type at least 4 characters
      </p>
      <p
        v-else-if="searchOpen && searchInputTrimmed.length >= 4 && !visibleConversations.length && !searchInProgress"
        class="conv-nav-empty"
      >
        No matches found
      </p>
      <p v-else-if="!conversations.length && !loading" class="conv-nav-empty">No conversations yet</p>
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

    <Transition name="conv-search-pop">
      <div v-if="searchOpen" class="conv-nav-search-shell" @click.stop>
        <input
          ref="searchInputRef"
          v-model="searchInput"
          class="conv-nav-search-input"
          type="search"
          inputmode="search"
          autocomplete="off"
          spellcheck="false"
          placeholder="Search conversation"
          aria-label="Search local conversations"
        />
      </div>
    </Transition>

    <div class="conv-nav-bottom">
      <SettingsMenu :collapsed="collapsed" />
      <DonateWidget />
      <button
        v-if="!collapsed"
        class="conv-nav-search-btn"
        :class="{ active: searchOpen }"
        :aria-label="searchOpen ? 'Finish search' : 'Open search'"
        :title="searchOpen ? 'Finish search' : 'Search conversations'"
        @click.stop="toggleSearch"
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
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
      </button>
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
import { computed, nextTick, onMounted, onUnmounted, ref, watch, type WatchStopHandle } from 'vue'
import { useRoute, useRouter, type RouteLocationRaw } from 'vue-router'
import { getConversation, listMyConversations, type ConversationSummary } from '../api'
import { useSSERegistry } from '../composables/useGlobalSSE'
import { cleanFileName } from '../utils/text'
import {
  searchConversations,
  type ConversationSearchHit,
  type SearchableConversation,
} from '../utils/conversationSearch'
import DonateWidget from './DonateWidget.vue'
import SettingsMenu from './SettingsMenu.vue'

const MIN_SEARCH_LENGTH = 4
const SEARCH_DEBOUNCE_MS = 700

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
const router = useRouter()
const conversations = ref<ConversationSummary[]>([])
const loading = ref(false)
const currentId = ref('')
const { getSSE, releaseSSE } = useSSERegistry()

const searchOpen = ref(false)
const searchInput = ref('')
const searchInputRef = ref<HTMLInputElement | null>(null)
const searchInProgress = ref(false)
const searchDataLoading = ref(false)
const searchHits = ref<ConversationSearchHit[]>([])
const searchDocuments = ref<SearchableConversation[]>([])
const searchInputTrimmed = computed(() => searchInput.value.trim())
const searchHitByConversationId = computed(
  () => new Map(searchHits.value.map((hit) => [hit.conversationId, hit])),
)

const visibleConversations = computed(() => {
  if (!searchOpen.value || searchInputTrimmed.value.length < MIN_SEARCH_LENGTH) {
    return conversations.value
  }
  const ids = new Set(searchHits.value.map((hit) => hit.conversationId))
  return conversations.value.filter((conversation) => ids.has(conversation.conversationId))
})

let searchWorker: Worker | null = null
let searchDebounceTimer: ReturnType<typeof setTimeout> | undefined
let searchRequestId = 0
let searchIndexPromise: Promise<void> | null = null
const lastSearchIndexSignature = ref('')

function clearSearchQueryFromRoute() {
  const nextQuery = { ...route.query }
  delete nextQuery.searchTerm
  delete nextQuery.searchMessageId
  delete nextQuery.searchMessageIndex
  if (Object.keys(nextQuery).length === Object.keys(route.query).length) return
  void router.replace({ path: route.path, query: nextQuery }).catch(() => {
    // Ignore navigation duplicates.
  })
}

function resetSearchState() {
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
    searchDebounceTimer = undefined
  }
  searchInput.value = ''
  searchHits.value = []
  searchInProgress.value = false
}

function finishSearch() {
  searchOpen.value = false
  resetSearchState()
  clearSearchQueryFromRoute()
}

function toggleSearch() {
  if (searchOpen.value) {
    finishSearch()
    return
  }
  searchOpen.value = true
  void ensureSearchIndex()
  void nextTick(() => searchInputRef.value?.focus())
}

function conversationRoute(conv: ConversationSummary): RouteLocationRaw {
  if (!searchOpen.value || searchInputTrimmed.value.length < MIN_SEARCH_LENGTH) {
    return `/c/${conv.conversationId}`
  }
  const hit = searchHitByConversationId.value.get(conv.conversationId)
  if (!hit) return `/c/${conv.conversationId}`
  return {
    path: `/c/${conv.conversationId}`,
    query: {
      searchTerm: searchInputTrimmed.value,
      ...(hit.firstMessageId ? { searchMessageId: hit.firstMessageId } : {}),
      searchMessageIndex: String(hit.firstMessageIndex),
    },
  }
}

async function ensureSearchIndex() {
  const signature = conversations.value.map((conversation) => conversation.conversationId).join('|')
  if (!signature) {
    searchDocuments.value = []
    lastSearchIndexSignature.value = ''
    return
  }
  if (signature === lastSearchIndexSignature.value && searchDocuments.value.length > 0) return
  if (searchIndexPromise) {
    await searchIndexPromise
    return
  }

  searchDataLoading.value = true
  searchIndexPromise = Promise.all(
    conversations.value.map(async (conversation) => {
      try {
        const fullConversation = await getConversation(conversation.conversationId)
        return {
          conversationId: conversation.conversationId,
          messages: fullConversation.messages.map((message, index) => ({
            messageId: message.id,
            index,
            content: message.content || '',
          })),
        } satisfies SearchableConversation
      } catch {
        return null
      }
    }),
  )
    .then((documents) => {
      const readyDocuments = documents.filter(
        (document): document is NonNullable<typeof document> => document !== null,
      )
      searchDocuments.value = readyDocuments
      lastSearchIndexSignature.value = signature
    })
    .finally(() => {
      searchDataLoading.value = false
      searchIndexPromise = null
    })

  await searchIndexPromise
}

async function runSearch(query: string) {
  if (query.length < MIN_SEARCH_LENGTH) {
    searchHits.value = []
    searchInProgress.value = false
    return
  }

  await ensureSearchIndex()
  const documents = searchDocuments.value
  if (!documents.length) {
    searchHits.value = []
    searchInProgress.value = false
    return
  }

  searchInProgress.value = true
  const currentRequestId = ++searchRequestId
  if (!searchWorker) {
    searchHits.value = searchConversations(documents, query)
    searchInProgress.value = false
    return
  }

  searchWorker.postMessage({
    requestId: currentRequestId,
    query,
    conversations: documents,
  })
}

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
    if (searchOpen.value) {
      await ensureSearchIndex()
      if (searchInputTrimmed.value.length >= MIN_SEARCH_LENGTH) {
        await runSearch(searchInputTrimmed.value)
      }
    }
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

watch(searchInputTrimmed, (query) => {
  if (!searchOpen.value) return
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
  if (query.length < MIN_SEARCH_LENGTH) {
    searchHits.value = []
    searchInProgress.value = false
    return
  }
  searchDebounceTimer = setTimeout(() => {
    void runSearch(query)
  }, SEARCH_DEBOUNCE_MS)
})

watch(searchOpen, (opened) => {
  if (!opened) return
  void ensureSearchIndex()
})

onMounted(() => {
  searchWorker = new Worker(new URL('../workers/conversationSearch.worker.ts', import.meta.url), {
    type: 'module',
  })
  searchWorker.onmessage = (event: MessageEvent<{ requestId: number; hits: ConversationSearchHit[] }>) => {
    const { requestId, hits } = event.data
    if (requestId !== searchRequestId) return
    searchHits.value = hits
    searchInProgress.value = false
  }
  searchWorker.onerror = () => {
    searchWorker = null
    searchInProgress.value = false
  }

  load()
  window.addEventListener('conversation-updated', load)
})

onUnmounted(() => {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
  if (searchWorker) {
    searchWorker.terminate()
    searchWorker = null
  }
  for (const [id, stop] of processingWatchers) {
    stop()
    releaseSSE(id)
  }
  processingWatchers.clear()
  window.removeEventListener('conversation-updated', load)
})
</script>
