<template>
  <div class="page" :class="{ 'shared-conversation-view': isViewer, 'embed-mode': isEmbed }">
    <ConversationHeader
      v-if="!isEmbed"
      :status="status"
      :conversation-id="conversationId"
      :conversation-title="conversationTitle"
      :can-upload="canUpload"
      :processing="loaded && status.status === 'processing'"
      :processing-step="processingStepLabel"
      :parsed-pages="parsedPages"
      :total-pages="totalPages"
      @renamed="status.displayName = $event"
      @reload="onReload"
      @view-threads="viewHeaderThreads"
    >
      <template #language-toggle>
        <LanguageToggle
          :messages="messages"
          :title="conversationTitle"
          :conversation-id="conversationId"
          @translated="onTranslated"
          @title-translated="onTitleTranslated"
          @restored="onRestored"
          @lang-changed="currentLanguage = $event"
          @translating-start="isTranslating = true"
          @translating-end="isTranslating = false"
        />
      </template>
      <template #auto-read-toggle>
        <button
          class="auto-read-btn"
          :class="{ active: autoReadEnabled }"
          :title="autoReadEnabled ? 'Disable auto-read' : 'Enable auto-read'"
          @click="toggleAutoRead"
        >
          <svg
            v-if="autoReadEnabled"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
            <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
            <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
          </svg>
          <svg
            v-else
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
            <line x1="23" y1="9" x2="17" y2="15" />
            <line x1="17" y1="9" x2="23" y2="15" />
          </svg>
        </button>
      </template>
    </ConversationHeader>

    <ErrorDetail
      v-if="status.status === 'failed'"
      :message="'Something went wrong while processing your files. Please try uploading again.'"
      :raw="status.errorMessage || undefined"
    />

    <div class="grid" style="grid-template-columns: 1fr">
      <section class="chat-panel">
        <div
          ref="chatContainer"
          class="chat-log"
          style="
            flex: 1;
            overflow-y: auto;
            overflow-x: hidden;
            display: flex;
            flex-direction: column;
            gap: 14px;
            padding-bottom: 12px;
          "
        >
          <div
            v-if="showCenteredProcessing"
            class="chat-log-centered-processing"
            role="status"
            aria-live="polite"
            aria-atomic="true"
          >
            <UploadingDots :text="processingLoaderLabel" />
          </div>
          <ChatMessageItem
            v-for="(msg, index) in displayedMessages"
            :key="messageRenderKey(msg, index)"
            :ref="
              (el) => {
                if (index === firstAssistantIndex)
                  firstMessageRef = el as InstanceType<typeof ChatMessageItem> | null
              }
            "
            :msg="msg"
            :all-messages="displayedMessages"
            :asking="assistantPending"
            :conversation-id="conversationId"
            :storage-conversation-id="storageConversationId"
            :is-welcome="isUploadMessage(index)"
            :is-first-message="index === 0 && msg.role === 'assistant' && !msg.isParentMessage"
            :can-upload="canUpload"
            :wiki-ready="wikiReady"
            :c4-ready="c4Ready"
            :files="uploadFilesForMessage(index)"
            :max-visible-actions="index === 0 ? 5 : 3"
            :conversation-name="conversationTitle"
            :file-name="primaryFileName"
            :lang="currentLanguage"
            :is-thread="isThread"
            :no-animation="index < initialMessageCount"
            :animate="index >= initialMessageCount && !!msg.id && !animatedMessageIds.has(msg.id)"
            :is-translating="isTranslating"
            :search-highlighted="isSearchHit(msg, index)"
            :search-term="searchTermFromRoute"
            :is-owner="status.role === 'owner' || status.role === 'editor'"
            @select-question="
              (q: string) => {
                question = q
                submitQuestion()
              }
            "
            @select-image-variant="handleSelectImageVariant"
            @upload-files="handleUploadFiles"
            @trigger-upload="triggerUploadOnFirstMessage"
            @view-threads="viewThreads"
            @image-revealed="(success) => onMessageImageRevealed(index, success)"
            @message-animated="onMessageAnimated(msg.id)"
            @show-wiki="openWikiModal"
            @show-c4="openC4Modal"
          />
          <div
            v-if="showInlineProcessing"
            class="chat-log-inline-processing"
            role="status"
            aria-live="polite"
            aria-atomic="true"
          >
            <UploadingDots :text="processingLoaderLabel" />
          </div>
        </div>

        <div v-if="roleLoaded && canReply" class="chat-input-bar">
          <div
            v-if="canUpload"
            class="upload-plus-btn"
            :data-tooltip="homeLang === 'pl' ? 'Prześlij więcej plików' : 'Upload more files'"
            @click="triggerUploadOnFirstMessage"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </div>
          <textarea
            ref="questionInput"
            v-model="question"
            class="chat-textarea"
            :placeholder="isViewer ? homeT.viewerReplyPlaceholder : homeT.askPlaceholder"
            rows="1"
            @input="autoResize"
            @keydown.enter.exact.prevent="submitQuestion"
            @paste="canUpload ? onPasteFile($event) : undefined"
          ></textarea>
          <button class="send-btn" :disabled="asking || !question.trim()" @click="submitQuestion">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
            </svg>
          </button>
        </div>
        <div v-else-if="roleLoaded" class="chat-readonly-notice">
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
          View only — reply to a message to start your own thread
        </div>
      </section>
    </div>
  </div>
  <WikiModal
    :visible="wikiModalOpen"
    :content="wikiContent"
    :loading="wikiLoading"
    :title="conversationTitle"
    @close="wikiModalOpen = false"
  />
  <ImageModal
    :visible="c4ModalOpen"
    :src="c4SvgUrl ?? ''"
    alt="Mapa Myśli"
    :stretch="true"
    @close="c4ModalOpen = false"
  />
</template>

<script setup lang="ts">
import {
  computed,
  onMounted,
  onUnmounted,
  onActivated,
  onDeactivated,
  ref,
  watch,
  nextTick,
} from 'vue'
import { AxiosError } from 'axios'
import {
  askQuestion,
  getConversation,
  uploadMoreFiles,
  addUrlToConversation,
  createConversationThread,
  saveConversationToken,
  extractError,
  getConversationWiki,
  type ConversationStatus,
  type ChatMessage,
} from '../api'
import { runImageGenStream } from '../composables/useImageGenStream'
import { cleanFileName } from '../utils/text'
import { getUserId } from '../utils/fingerprint'
import { getData, setData } from '../utils/localData'
import { useRoute, useRouter } from 'vue-router'
import ConversationHeader from '../components/ConversationHeader.vue'
import ChatMessageItem from '../components/ChatMessage.vue'
import WikiModal from '../components/WikiModal.vue'
import ImageModal from '../components/ImageModal.vue'
import ErrorDetail from '../components/ErrorDetail.vue'
import LanguageToggle from '../components/LanguageToggle.vue'
import UploadingDots from '../components/UploadingDots.vue'
import { useTextSelectionSpeech } from '../composables/useTextSelectionSpeech'
import { useAutoRead } from '../composables/useAutoRead'
import { useSSE } from '../composables/useGlobalSSE'
import { IMAGE_GEN_REGEX } from '../utils/markdown'
import { homeT, homeLang } from '../i18n/homeLocale'
import { getStoredConversationLanguage } from '../utils/conversationLanguage'

type ProcessingStep = 'generating_welcome' | 'indexing_pages' | ''
const STEP_LABELS: Record<ProcessingStep, string> = {
  generating_welcome: 'Processing',
  indexing_pages: 'Indexing pages for Q&A',
  '': '',
}
const IMAGE_MIME_PREFIXES = ['image/']
function isImageOnlyUpload(files: ConversationStatus['files']): boolean {
  return files.length > 0 && files.every((f) => IMAGE_MIME_PREFIXES.some((p) => f.mimeType.startsWith(p)))
}
function stepLabel(step: ProcessingStep, imageOnly = false): string {
  if (step === 'indexing_pages' && imageOnly) return 'Analyzing image'
  return STEP_LABELS[step] || ''
}
import { newContent } from '../composables/newContent'
import {
  attachRenderKey,
  buildRenderKeyIndex,
  copyWithStableRenderKeys,
  nextMessageRenderKey,
  type MessageWithRenderKey,
} from '../utils/messageRenderKey'

const props = defineProps<{ conversationId: string }>()

defineOptions({ name: 'ConversationPage' })

const conversationId = props.conversationId
const question = ref('')
const asking = ref(false)
const questionInput = ref<HTMLTextAreaElement | null>(null)
const chatContainer = ref<HTMLDivElement | null>(null)

// Holds a generated-image file name to pass as a reference when the user
// clicks "Generate next variant 🎨". Cleared immediately after being consumed
// by ask() so it only affects the next single generation call.
const pendingRefImageFileNames = ref<string[]>([])

const currentLanguage = ref('')
const isTranslating = ref(false)

const wikiReady = ref(false)
const wikiModalOpen = ref(false)
const wikiContent = ref<string | null>(null)
const wikiLoading = ref(false)

const c4Ready = ref(false)
const c4ModalOpen = ref(false)
// Cached SVG string: rendered once on first open, reused on subsequent opens.
const c4SvgCache = ref<string | null>(null)
// Blob URL for ImageModal lightbox — created from c4SvgCache, revoked on close.
const c4SvgUrl = ref<string | null>(null)

const status = ref<ConversationStatus>({
  conversationId,
  displayName: null,
  status: 'processing',
  role: 'viewer',
  parentMessageId: null,
  parentConversationId: null,
  files: [],
  messages: [],
  accessRequests: [],
})
const messages = ref<MessageWithRenderKey<ChatMessage>[]>([])
const initialMessageCount = ref(Infinity)
const hasLocalError = ref(false)

// Tracks which assistant message IDs have already had their word-reveal
// animation played. Cleared only on full page navigation. Using IDs (not
// indices) so the set stays correct after array replacements on reload.
const animatedMessageIds = ref(new Set<string>())
// Suppresses image-load-triggered auto-scroll briefly after translation is
// applied. When translation updates message content, TextFade remounts
// MessageContent (key change), causing images inside to reload. These image
// load events can trigger scrollToBottom for messages added after initial page
// load. We suppress that scroll for a short window after translation.
let suppressImageScrollTimer: ReturnType<typeof setTimeout> | null = null
let suppressImageScrollAfterTranslation = false

function markTranslationApplied() {
  suppressImageScrollAfterTranslation = true
  if (suppressImageScrollTimer) clearTimeout(suppressImageScrollTimer)
  suppressImageScrollTimer = setTimeout(() => {
    suppressImageScrollAfterTranslation = false
  }, 2000)
}

function onMessageAnimated(msgId: string | undefined) {
  if (msgId) animatedMessageIds.value.add(msgId)
}

function messageRenderKey(msg: MessageWithRenderKey<ChatMessage>, index: number) {
  return msg.__renderKey ?? (msg.id ? `server:${msg.id}` : `server-index:${index}`)
}

// While the backend is generating the assistant reply, the most recent server
// message is still the user's question. After a page refresh we keep the
// typing dots visible by appending a virtual empty assistant bubble.
const assistantPending = computed(() => {
  if (asking.value) return true
  if (hasLocalError.value) return false
  if (status.value.status === 'failed') return false
  const last = messages.value[messages.value.length - 1]
  return last?.role === 'user'
})

const displayedMessages = computed<MessageWithRenderKey<ChatMessage>[]>(() => {
  if (assistantPending.value && !asking.value) {
    return [...messages.value, { role: 'assistant', content: '' }]
  }
  return messages.value
})

// Welcome message content used as TTS tone instructions
const welcomeMessageContent = computed(() => {
  const idx = messages.value.findIndex((_, i) => isUploadMessage(i))
  return idx >= 0 ? messages.value[idx].content : ''
})

// Enable text-to-speech tooltip for selected text within chat messages
// Only active when current display language differs from browser language
useTextSelectionSpeech(chatContainer, currentLanguage, welcomeMessageContent, messages)

// Auto-read: when enabled, reads assistant responses and welcome messages aloud
const {
  enabled: autoReadEnabled,
  toggle: toggleAutoRead,
  readWelcomeIfEnabled,
  cleanup: cleanupAutoRead,
} = useAutoRead(messages, asking, welcomeMessageContent, chatContainer, currentLanguage)

// SSE: one global multiplexed connection, one ref per conversation.
// The ref is mutated by useGlobalSSE whenever an event arrives; watching it
// replaces the individual callback-based API from useConversationEvents.
const processingStep = ref<ProcessingStep>('generating_welcome')
const parsedPages = ref(0)
const totalPages = ref(0)

const { sse: sseEvent } = useSSE(conversationId)

watch(sseEvent, (evt) => {
  if (!evt) return
  switch (evt.event) {
    case 'welcome_message':
      processingStep.value = 'indexing_pages'
      loadConversation()
      break
    case 'complete':
      processingStep.value = ''
      loadConversation()
      break
    case 'page_progress':
      parsedPages.value = (evt.data.parsed as number) ?? parsedPages.value
      totalPages.value = (evt.data.total as number) ?? totalPages.value
      break
    case 'message_appended':
      loadConversation()
      break
    case 'wiki_ready':
      wikiReady.value = true
      break
  }
})

// Set c4Ready as soon as the welcome message contains an embedded [mindmap].
// This fires immediately when the welcome SSE lands — no extra round-trip needed.
watch(
  welcomeMessageContent,
  (content) => {
    if (!c4Ready.value && content && /\[(?:mindmap|mapa myśli)\][\s\S]*?\[\/(?:mindmap|mapa myśli)\]/.test(content)) {
      c4Ready.value = true
    }
  },
  { immediate: true },
)

const processingStepLabel = computed(() =>
  stepLabel(processingStep.value, isImageOnlyUpload(status.value.files)),
)

// Loader text shown in the centered (empty state) and inline (below messages)
// processing indicators.  Reflects live SSE page-progress updates so users see
// "Parsed pages: 400 / 650" rather than a static "Processing…" label.
const processingLoaderLabel = computed(() => {
  const baseLabel = processingStepLabel.value || 'Processed'
  if (totalPages.value > 0) {
    return `${baseLabel} ${parsedPages.value} / ${totalPages.value} pages`
  }
  return baseLabel
})

const firstMessageRef = ref<InstanceType<typeof ChatMessageItem> | null>(null)
// Index of the first assistant message in displayedMessages — used to wire
// the [upload] inline action to a ChatMessage that actually mounts the hidden
// <input type="file">. The very first message can be a user turn (e.g. when the
// conversation was started by typing a question instead of uploading files),
// in which case targeting index 0 yields a no-op click.
const firstAssistantIndex = computed(() =>
  displayedMessages.value.findIndex((m) => m.role === 'assistant'),
)
const loaded = ref(false)
const routerInstance = useRouter()
const route = useRoute()
const isEmbed = computed(() => route.query.embed === '1')

const searchTermFromRoute = ref('')
const searchMessageIdFromRoute = ref('')
const searchMessageIndexFromRoute = ref<number | null>(null)

function parseSearchMessageIndex(rawValue: unknown): number | null {
  if (typeof rawValue !== 'string') return null
  const parsed = Number.parseInt(rawValue, 10)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null
}

function syncSearchFromRoute() {
  searchTermFromRoute.value = typeof route.query.searchTerm === 'string' ? route.query.searchTerm : ''
  searchMessageIdFromRoute.value =
    typeof route.query.searchMessageId === 'string' ? route.query.searchMessageId : ''
  searchMessageIndexFromRoute.value = parseSearchMessageIndex(route.query.searchMessageIndex)
}

function isSearchHit(msg: MessageWithRenderKey<ChatMessage>, index: number): boolean {
  if (!searchTermFromRoute.value) return false
  if (searchMessageIdFromRoute.value) return msg.id === searchMessageIdFromRoute.value
  return searchMessageIndexFromRoute.value === index
}

const isThread = computed(() => !!status.value.parentMessageId)

// For threads, files live under the parent conversation's storage namespace
const storageConversationId = computed(() => status.value.storageNamespace || conversationId)

// Translation state
const originalMessages = ref<Map<number, string>>(new Map())
const originalDisplayName = ref<string | null>(null)

function onTranslated(translations: Map<number, string>) {
  // Save originals before replacing
  translations.forEach((_, i) => {
    if (!originalMessages.value.has(i)) {
      originalMessages.value.set(i, messages.value[i].content)
    }
  })
  // Apply translations
  translations.forEach((text, i) => {
    messages.value[i].content = text
  })
  // Prevent image reloads (caused by TextFade remount) from triggering auto-scroll
  markTranslationApplied()
}

function onTitleTranslated(translated: string) {
  // Save original displayName only on first translation, then swap. When the
  // title is purely derived from file names (no displayName) we still set
  // displayName so the translated version persists until restore.
  if (originalDisplayName.value === null) {
    originalDisplayName.value = status.value.displayName
  }
  status.value.displayName = translated
}

function onRestored(newTranslations: Map<number, string>) {
  // Prevent image reloads triggered by restoring content from triggering auto-scroll
  markTranslationApplied()
  // Restore originally translated messages
  originalMessages.value.forEach((text, i) => {
    if (messages.value[i]) {
      messages.value[i].content = text
    }
  })
  originalMessages.value.clear()

  // Apply translations for messages added during translated state
  // (e.g., user asked in Polish while viewing Polish translation — translate to English on restore)
  if (newTranslations.size) {
    newTranslations.forEach((text, i) => {
      if (messages.value[i]) {
        messages.value[i].content = text
      }
    })
  }

  // Restore original title
  if (originalDisplayName.value !== null) {
    status.value.displayName = originalDisplayName.value
    originalDisplayName.value = null
  }
}

// Viewer mode: when a viewer opens a shared conversation, show a hello message and let them reply
const isViewer = computed(
  () =>
    status.value.role === 'viewer' &&
    !status.value.parentMessageId &&
    !status.value.parentConversationId,
)

const roleLoaded = ref(false)
const canUpload = computed(() => status.value.role === 'owner' || status.value.role === 'editor')
const canReply = computed(
  () => status.value.role === 'owner' || status.value.role === 'editor' || isViewer.value,
)
const showCenteredProcessing = computed(
  () => loaded.value && status.value.status === 'processing' && messages.value.length === 0,
)
// Once the early welcome message arrives we still want to show a live
// progress indicator until indexing completes.  The centered one disappears
// as soon as there are messages, so render an inline loader right after the
// last message with live "Parsed X / Y pages" stats.
const showInlineProcessing = computed(
  () => loaded.value && status.value.status === 'processing' && messages.value.length > 0,
)

function isUploadMessage(index: number): boolean {
  const msg = messages.value[index]
  if (msg?.role !== 'assistant') return false
  // Parent message in a thread should only be treated as upload/welcome
  // when it explicitly references uploaded files.
  if (msg.isParentMessage) return !!msg.uploadedFileNames?.length
  // Has explicit uploadedFileNames from backend
  if (msg.uploadedFileNames?.length) return true
  // Legacy: first message is a welcome message if it's from the assistant with no preceding user message
  return index === 0
}

function uploadFilesForMessage(index: number): ConversationStatus['files'] | undefined {
  const msg = messages.value[index]
  if (!isUploadMessage(index)) return undefined
  // If message has explicit file names, match them against status.files
  if (msg.uploadedFileNames?.length) {
    const nameSet = new Set(msg.uploadedFileNames)
    return status.value.files.filter((f) => nameSet.has(f.originalName))
  }
  // Legacy: first welcome message without uploadedFileNames gets all files
  // that aren't claimed by later upload messages
  const claimedNames = new Set<string>()
  for (const m of messages.value) {
    if (m !== msg && m.uploadedFileNames?.length) {
      m.uploadedFileNames.forEach((n) => claimedNames.add(n))
    }
  }
  return status.value.files.filter((f) => !claimedNames.has(f.originalName))
}

const conversationTitle = computed(() => {
  if (status.value.displayName) return status.value.displayName
  if (status.value.files.length) {
    return status.value.files.map((f) => cleanFileName(f.originalName)).join(', ')
  }
  return ''
})

const primaryFileName = computed(() => {
  if (status.value.files.length) return status.value.files[0].originalName
  return ''
})

watch(
  conversationTitle,
  (title) => {
    document.title = title ? `${title} | chatrag.app` : 'chatrag.app'
  },
  { immediate: true },
)

let isLoadingConversation = false

// Thin wrapper that prevents concurrent calls. If the network throws, the
// error propagates to the caller so onActivated can gracefully fall back to
// the cached state, while onMounted / SSE callbacks still surface the error.
async function loadConversation() {
  if (isLoadingConversation) return
  isLoadingConversation = true
  return doLoadConversation().finally(() => {
    isLoadingConversation = false
  })
}

async function doLoadConversation() {
  const response = await getConversation(conversationId)
  status.value = response

  // Keep processingStep in sync with the DB state so the UI recovers when
  // SSE events were missed (e.g. worker finished while the tab was closed).
  if (response.status === 'ready' || response.status === 'failed') {
    processingStep.value = ''
    // Background-check for an existing wiki so the button shows on page load
    // without waiting for a wiki_ready SSE (which only fires during indexing).
    if (!wikiReady.value) {
      getConversationWiki(conversationId)
        .then((c) => {
          if (c) wikiReady.value = true
        })
        .catch(() => {})
    }
  } else if (response.status === 'processing' && processingStep.value === 'generating_welcome') {
    // Advance to 'indexing_pages' if a welcome message already exists in the
    // DB — this means the worker sent the welcome event before this page load.
    const serverMessages = (response.messages || []) as ChatMessage[]
    if (serverMessages.some((m) => m.role === 'assistant')) {
      processingStep.value = 'indexing_pages'
    }
  }

  const existingRenderKeysById = buildRenderKeyIndex(messages.value)

  // Viewer mode: show the original welcome message + a virtual hello message
  const viewerMode =
    response.role === 'viewer' && !response.parentMessageId && !response.parentConversationId
  if (viewerMode) {
    if (messages.value.length === 0) {
      const name = response.displayName || 'this topic'
      const serverMessages = response.messages || []
      const firstWelcome = serverMessages.find((m: ChatMessage) => m.role === 'assistant')

      const viewerMessages: MessageWithRenderKey<ChatMessage>[] = []

      // 1st message: original welcome message (same as owner sees, with file previews)
      if (firstWelcome) {
        viewerMessages.push({
          ...firstWelcome,
          __renderKey: firstWelcome.id ? `server:${firstWelcome.id}` : 'viewer-welcome',
        })
      }

      // 2nd message: virtual hello. Action buttons live inline in the
      // welcome message above — the hello stays a plain greeting.
      viewerMessages.push({
        role: 'assistant',
        content: `Hi! How can I help you with **${name}**?`,
        __renderKey: 'viewer-hello',
      })

      messages.value = viewerMessages
    }
    loaded.value = true
    if (initialMessageCount.value === Infinity) {
      initialMessageCount.value = messages.value.length
    }
    return
  }

  if (!asking.value && !hasLocalError.value) {
    const serverMessages = response.messages || []
    const stableServerMessages = copyWithStableRenderKeys(serverMessages, existingRenderKeysById)
    if (originalMessages.value.size > 0) {
      // In translated mode: preserve translated content for existing messages
      // Update originals with fresh server data
      originalMessages.value.forEach((_, i) => {
        if (stableServerMessages[i]) {
          originalMessages.value.set(i, stableServerMessages[i].content)
        }
      })
      // Append any new messages from server (not yet translated)
      for (let i = messages.value.length; i < stableServerMessages.length; i++) {
        messages.value.push(stableServerMessages[i])
      }
    } else if (stableServerMessages.length !== messages.value.length) {
      messages.value = stableServerMessages
    } else {
      // Sync per-message metadata that may arrive after initial message creation.
      for (let i = 0; i < stableServerMessages.length; i++) {
        const srv = stableServerMessages[i]
        const local = messages.value[i]
        if (srv.uploadedFileNames?.length && !local.uploadedFileNames?.length) {
          local.uploadedFileNames = srv.uploadedFileNames
        }
      }
    }
  }
  loaded.value = true
  if (initialMessageCount.value === Infinity) {
    initialMessageCount.value = messages.value.length
  }
}

async function onReload() {
  hasLocalError.value = false
  await loadConversation()
  window.dispatchEvent(new CustomEvent('conversation-updated'))
}

async function handleUploadFiles(files: File[]) {
  const msgRef = firstMessageRef.value
  if (!msgRef) return
  msgRef.setUploading(true)
  try {
    await uploadMoreFiles(conversationId, files)
    msgRef.resetUploadState()
    await onReload()
  } catch (err: unknown) {
    if (err instanceof AxiosError && err.response?.status === 409) {
      const names = (
        ((err.response.data as Record<string, unknown>)?.duplicates as string[]) || []
      ).join(', ')
      msgRef.resetUploadState(names ? `File ${names} already uploaded` : 'File already uploaded')
    } else {
      const { message } = extractError(err)
      msgRef.resetUploadState(message || 'Upload failed')
    }
  }
}

function triggerUploadOnFirstMessage() {
  firstMessageRef.value?.triggerUpload()
}

function viewThreads(messageId: string) {
  // Navigate to the shared message page to see all threads
  routerInstance.push(`/m/${messageId}`)
}

function viewHeaderThreads() {
  // Find the first message that has threads and navigate to its shared view
  const msg = messages.value.find((m) => m.threadReplyCount && m.threadReplyCount > 0 && m.id)
  if (msg) {
    routerInstance.push(`/m/${msg.id}`)
  }
}

function scrollToElement(container: HTMLElement, element: HTMLElement, smooth = true) {
  const containerTop = container.getBoundingClientRect().top
  const elementTop = element.getBoundingClientRect().top

  const currentScroll = container.scrollTop
  const target = elementTop - containerTop + currentScroll

  container.scrollTo({
    top: target,
    behavior: smooth ? 'smooth' : 'instant',
  })
}

function scrollToBottom(smooth = false, toEnd = false, showUserQuestion = false) {
  if (!chatContainer.value) return
  const container = chatContainer.value

  // When `showUserQuestion` is true (and not forced to end), scroll so the
  // last user message is at the top of the container — keeps the question
  // visible while the response flows below it.
  if (showUserQuestion && !toEnd) {
    const users = document.querySelectorAll('.chat-log .message-row.user')
    const user = users[users.length - 1] as HTMLElement | undefined
    const chatLog = document.querySelector('.chat-log') as HTMLElement | null
    if (chatLog && user) {
      scrollToElement(chatLog, user, smooth)
      return
    }
  }

  // Default: scroll all the way to the bottom (new response arrived, image
  // loaded, initial mount, or showUserQuestion with no user message found).
  container.scrollTo({
    top: container.scrollHeight,
    behavior: smooth ? 'smooth' : 'instant',
  })
}

function scrollToSearchHit() {
  if (!chatContainer.value || !searchTermFromRoute.value) return
  const container = chatContainer.value
  let target: HTMLElement | null = null

  if (searchMessageIdFromRoute.value) {
    target = container.querySelector(
      `.message-row[data-message-id="${searchMessageIdFromRoute.value}"]`,
    ) as HTMLElement | null
  }

  if (!target && searchMessageIndexFromRoute.value !== null) {
    const rows = container.querySelectorAll('.message-row')
    target = (rows[searchMessageIndexFromRoute.value] as HTMLElement | undefined) || null
  }

  if (!target) return
  scrollToElement(container, target)
}

function onMessageImageRevealed(index: number, success: boolean) {
  if (!success) return
  // Only auto-follow images for newly-arrived messages.
  // Historical messages can emit image load events during initial render or
  // after translation remounts their content.
  if (index < initialMessageCount.value) return
  if (suppressImageScrollAfterTranslation) return
  scrollToBottom(true, true)
}

async function ask() {
  if (!question.value.trim()) return

  // If the user typed a lone URL, add it to the conversation as a new source
  const trimmed = question.value.trim()
  if (/^https?:\/\/\S+$/.test(trimmed) && !trimmed.includes(' ')) {
    question.value = ''
    asking.value = true
    try {
      await addUrlToConversation(conversationId, trimmed)
      // Poll until the conversation is back to 'ready' with the welcome message
      await loadConversation()
    } catch (err: unknown) {
      const { message, raw } = extractError(err)
      messages.value.push({
        role: 'assistant',
        content: `⚠️ Error loading URL: ${message}\n\n<details><summary>Show details</summary>\n\n\`\`\`\n${raw}\n\`\`\`\n</details>`,
      })
    } finally {
      asking.value = false
    }
    return
  }

  if (status.value.status !== 'ready') {
    // Allow questions once the welcome message has arrived (indexing still in progress).
    // The RAG will answer with whatever chunks are available so far.
    const hasWelcome = messages.value.some((m) => m.role === 'assistant')
    if (!hasWelcome) {
      await loadConversation()
      return
    }
  }

  // Viewer mode: create a new conversation thread and navigate to it
  if (isViewer.value) {
    const userId = getUserId()
    if (!userId) return
    asking.value = true
    const pendingQuestion = question.value.trim()
    question.value = ''
    try {
      const result = await createConversationThread(conversationId, userId)
      saveConversationToken(result.conversationId, result.ownerPassword)
      routerInstance.push({ path: `/c/${result.conversationId}`, state: { pendingQuestion } })
    } catch (err: unknown) {
      hasLocalError.value = true
      const { message, raw } = extractError(err)
      messages.value.push({
        role: 'assistant',
        content: `⚠️ Error: ${message}\n\n<details><summary>Show details</summary>\n\n\`\`\`\n${raw}\n\`\`\`\n</details>`,
      })
    } finally {
      asking.value = false
    }
    return
  }

  asking.value = true
  hasLocalError.value = false
  const currentQuestion = question.value
  const promptLanguage =
    currentLanguage.value || getStoredConversationLanguage(conversationId) || undefined
  question.value = ''
  const optimisticUserMessage: MessageWithRenderKey<ChatMessage> = {
    role: 'user',
    content: currentQuestion,
  }
  messages.value.push(attachRenderKey(optimisticUserMessage, nextMessageRenderKey('local-user')))

  const optimisticAssistantMessage: MessageWithRenderKey<ChatMessage> = {
    role: 'assistant',
    content: '',
  }
  messages.value.push(
    attachRenderKey(optimisticAssistantMessage, nextMessageRenderKey('local-assistant')),
  )
  // Use the reactive proxy so Vue detects content updates immediately
  const reactiveMsg = messages.value[messages.value.length - 1]

  const TIMEOUT_MS = 120_000 // 2 minutes max for an answer
  try {
    const timeout = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error('Request timed out')), TIMEOUT_MS),
    )
    const isImageGen = IMAGE_GEN_REGEX.test(currentQuestion)
    const refFileNames = pendingRefImageFileNames.value.slice()
    pendingRefImageFileNames.value = []
    const response = isImageGen
      ? await runImageGenStream({
          conversationId,
          question: currentQuestion,
          reactiveMsg,
          timeoutMs: TIMEOUT_MS,
          language: promptLanguage,
          referenceImageFileNames: refFileNames.length ? refFileNames : undefined,
          onAnnouncement: () => {
            nextTick(() => scrollToBottom(true, false, true))
          },
        })
      : await Promise.race([
          askQuestion(
            conversationId,
            currentQuestion,
            getUserId() || undefined,
            promptLanguage,
          ),
          timeout,
        ])
    reactiveMsg.generatingImage = false
    reactiveMsg.imagePartialDataUrl = undefined
    reactiveMsg.imageDetailedPrompt = undefined
    reactiveMsg.content = response.answer
    reactiveMsg.citations = response.citations
    if (response.assistantMessageId) reactiveMsg.id = response.assistantMessageId
    // Also assign user message id
    const userMsg = messages.value[messages.value.length - 2]
    if (response.userMessageId && userMsg?.role === 'user') userMsg.id = response.userMessageId
    await loadConversation()
    await nextTick()
    requestAnimationFrame(() => requestAnimationFrame(() => scrollToBottom(true, true)))
  } catch (err: unknown) {
    reactiveMsg.generatingImage = false
    reactiveMsg.imageDetailedPrompt = undefined
    if (IMAGE_GEN_REGEX.test(currentQuestion)) {
      const openaiMessage = (err as any)?.openaiMessage
      reactiveMsg.content = openaiMessage
        ? `Sorry, there was an error during generating image. Refresh page or try again.\n\n> ${openaiMessage}`
        : 'Sorry, there was an error during generating image. Refresh page or try again.'
    } else {
      const { message, raw } = extractError(err)
      reactiveMsg.content = `⚠️ Error: ${message}\n\n<details><summary>Show details</summary>\n\n\`\`\`\n${raw}\n\`\`\`\n</details>`
    }
    hasLocalError.value = true
  } finally {
    asking.value = false
  }
}

function submitQuestion() {
  if (asking.value || !question.value.trim()) return
  ask()
  if (questionInput.value) {
    questionInput.value.style.height = 'auto'
  }
  newContent.value = true
}

function handleSelectImageVariant(label: string, refFileName: string) {
  question.value = label
  pendingRefImageFileNames.value = [refFileName]
  submitQuestion()
}

function autoResize(e: Event) {
  const el = e.target as HTMLTextAreaElement
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}

function onPasteFile(event: ClipboardEvent) {
  const items = event.clipboardData?.items
  if (!items) return

  const files: File[] = []
  for (const item of Array.from(items)) {
    if (item.kind !== 'file') continue
    const type = item.type
    if (!type.startsWith('image/') && type !== 'application/pdf' && type !== 'text/plain') continue
    const raw = item.getAsFile()
    if (!raw) continue
    // Pasted screenshots have an empty name; give them a readable timestamp-based name
    const ext = type.split('/')[1] ?? 'bin'
    const name = raw.name || `pasted-${Date.now()}.${ext}`
    const file = raw.name ? raw : new File([raw], name, { type: raw.type })
    files.push(file)
  }

  if (files.length === 0) return
  event.preventDefault()
  handleUploadFiles(files)
}

// --- Scroll position persistence ---
const SCROLL_POS_KEY = 'scrollPositions'

function saveScrollPosition() {
  if (!chatContainer.value) return
  const c = chatContainer.value
  const maxScroll = c.scrollHeight - c.clientHeight
  if (maxScroll <= 0) return
  const ratio = c.scrollTop / maxScroll
  const all = getData<Record<string, number>>(SCROLL_POS_KEY) || {}
  all[conversationId] = ratio
  setData(SCROLL_POS_KEY, all)
}

function restoreScrollPosition(): boolean {
  if (!chatContainer.value) return false
  const all = getData<Record<string, number>>(SCROLL_POS_KEY)
  const ratio = all?.[conversationId]
  if (ratio == null) return false
  const c = chatContainer.value
  const maxScroll = c.scrollHeight - c.clientHeight
  if (maxScroll <= 0) return false
  c.scrollTo({ top: ratio * maxScroll, behavior: 'instant' })
  return true
}

let scrollSaveTimer: ReturnType<typeof setTimeout> | undefined
let statusPollingInterval: ReturnType<typeof setInterval> | undefined
function onChatScroll() {
  if (scrollSaveTimer) clearTimeout(scrollSaveTimer)
  scrollSaveTimer = setTimeout(saveScrollPosition, 300)
}

let prevMessageCount = 0
const conversationReady = ref(false)

// Auto-read welcome message only for fresh conversations (no prior user messages)
let welcomeReadTriggered = false
watch(
  () => status.value.status,
  (newStatus) => {
    const hasUserMessages = messages.value.some((m) => m.role === 'user')
    if (
      newStatus === 'ready' &&
      !welcomeReadTriggered &&
      messages.value.length > 0 &&
      !hasUserMessages
    ) {
      welcomeReadTriggered = true
      readWelcomeIfEnabled()
    }
  },
)

watch(
  () => messages.value.length,
  (newLen) => {
    if (conversationReady.value && newLen > prevMessageCount) {
      // Show user question at top so the response streams into view below it
      scrollToBottom(false, false, true)
    }
    prevMessageCount = newLen

    if (searchTermFromRoute.value) scrollToSearchHit()
  },
  { flush: 'post' },
)

watch(
  () => route.query,
  () => {
    syncSearchFromRoute()
    if (!searchTermFromRoute.value) return
    scrollToSearchHit()
  },
  { immediate: true, flush: 'post' },
)

async function openWikiModal() {
  wikiModalOpen.value = true
  if (!wikiContent.value) {
    wikiLoading.value = true
    try {
      wikiContent.value = await getConversationWiki(conversationId)
    } finally {
      wikiLoading.value = false
    }
  }
}

async function openC4Modal() {
  c4ModalOpen.value = true
  if (c4SvgCache.value) return  // already rendered, reuse cache

  const match = welcomeMessageContent.value.match(/\[(?:mindmap|mapa myśli)\]([\s\S]*?)\[\/(?:mindmap|mapa myśli)\]/)
  if (!match) return

  // Strip ```mermaid fences if the LLM wrapped the code block
  // Strip emoji characters (including variation selectors like U+FE0F) which
  // Mermaid's mindmap lexer does not support.
  // Use [^\S\n]* instead of \s* so that newlines (which encode indentation
  // hierarchy) are never consumed — only horizontal whitespace is stripped.
  // Also normalise single-brace hexagon nodes {Label} → {{Label}} since the
  // LLM occasionally emits single braces which are an unrecognised token.
  const mermaidCode = match[1]
    .replace(/\\n/g, '\n')  // normalize escaped newlines that may come through JSON/SSE
    .trim()
    .replace(/^```mermaid\n?/, '')
    .replace(/\n?```$/, '')
    .replace(/[\p{Emoji_Presentation}\p{Extended_Pictographic}]\uFE0F?[^\S\n]*/gu, '')
    .replace(/(\w)\{(?!\{)([^{}\n]+)\}(?!\})/g, '$1{{$2}}')
    .trim()
  if (!mermaidCode) return

  try {
    const mod = await import('mermaid')
    const m = mod.default
    m.initialize({
      startOnLoad: false,
      theme: 'base',
      themeVariables: {
        darkMode: false,
        background: '#f8fafc',
        primaryColor: '#ede9fe',
        primaryTextColor: '#000000',
        primaryBorderColor: '#7c3aed',
        secondaryColor: '#e2e8f0',
        secondaryTextColor: '#000000',
        tertiaryColor: '#f1f5f9',
        tertiaryTextColor: '#000000',
        lineColor: '#475569',
        textColor: '#000000',
        nodeTextColor: '#000000',
        labelTextColor: '#000000',
      },
      securityLevel: 'loose',
      suppressErrorRendering: true,
    })
    const { svg } = await m.render(`mindmap-modal-${Date.now()}`, mermaidCode)
    c4SvgCache.value = svg
    // Strip fixed width/height from the SVG root so CSS controls sizing.
    // Mermaid outputs absolute pixel values; without this the <img> uses those
    // intrinsic dimensions and appears tiny on narrow screens.
    const scalableSvg = svg.replace(/<svg([^>]*)>/, (_m, attrs: string) =>
      '<svg' + attrs.replace(/\s+(width|height)="[^"]*"/g, '') + '>',
    )
    // Revoke previous blob URL before creating a new one
    if (c4SvgUrl.value) URL.revokeObjectURL(c4SvgUrl.value)
    c4SvgUrl.value = URL.createObjectURL(new Blob([scalableSvg], { type: 'image/svg+xml' }))
  } catch (e) {
    console.error('[Mapa Myśli] Failed to render mindmap SVG:', e)
  }
}

onMounted(async () => {
  syncSearchFromRoute()
  await loadConversation()
  loaded.value = true
  roleLoaded.value = true
  await nextTick()
  // Restore saved scroll position, or fall back to scrolling to bottom
  if (!restoreScrollPosition()) {
    scrollToBottom()
  }
  if (searchTermFromRoute.value) {
    requestAnimationFrame(scrollToSearchHit)
  }
  prevMessageCount = messages.value.length
  conversationReady.value = true

  // Listen for scroll events to persist position
  chatContainer.value?.addEventListener('scroll', onChatScroll, { passive: true })

  // Poll every 30 s while processing so we recover from missed SSE events
  // (e.g. worker finished while the browser tab was hidden or disconnected).
  statusPollingInterval = setInterval(async () => {
    if (status.value.status === 'processing') {
      await loadConversation()
    }
  }, 30_000)

  // Auto-submit pending question from thread creation
  const pending = window.history.state?.pendingQuestion as string | undefined
  if (pending) {
    question.value = pending
    // Clear it from history state to prevent re-submit on refresh
    const cleanState = { ...window.history.state }
    delete cleanState.pendingQuestion
    window.history.replaceState(cleanState, '')
    await nextTick()
    submitQuestion()
  }
})

onUnmounted(() => {
  chatContainer.value?.removeEventListener('scroll', onChatScroll)
  if (scrollSaveTimer) clearTimeout(scrollSaveTimer)
  if (suppressImageScrollTimer) clearTimeout(suppressImageScrollTimer)
  if (statusPollingInterval) clearInterval(statusPollingInterval)
  cleanupAutoRead()
})

// KeepAlive lifecycle hooks.
// onActivated fires on first mount AND on every navigation back to a cached
// page. onDeactivated fires when navigating away from a cached page.
// We skip the first activation because onMounted already did the initial
// load + SSE connect. On subsequent activations we reload fresh from the
// server (falling back to the cached state on network errors) and reconnect
// the SSE stream that was closed during deactivation.
let hasActivated = false

onActivated(async () => {
  if (!hasActivated) {
    hasActivated = true
    return
  }
  // Reload from server when navigating back to a cached page.
  // The SSE subscription stays active while cached so background events
  // still update the ref; this call ensures state is fresh on re-entry.
  try {
    await loadConversation()
  } catch {
    // Network error – keep the cached state visible rather than crashing
  }
  // Restart polling if the conversation is still processing.
  if (status.value.status === 'processing' && !statusPollingInterval) {
    statusPollingInterval = setInterval(async () => {
      if (status.value.status === 'processing') {
        await loadConversation()
      }
    }, 30_000)
  }
})

onDeactivated(() => {
  saveScrollPosition()
  if (scrollSaveTimer) {
    clearTimeout(scrollSaveTimer)
    scrollSaveTimer = undefined
  }
  if (statusPollingInterval) {
    clearInterval(statusPollingInterval)
    statusPollingInterval = undefined
  }
})
</script>
