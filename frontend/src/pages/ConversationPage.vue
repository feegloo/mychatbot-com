<template>
  <div class="page" :class="{ 'shared-conversation-view': isViewer }">
    <ConversationHeader
      ref="headerRef"
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
          :suggested-questions="allSuggestedQuestions"
          :conversation-id="conversationId"
          @translated="onTranslated"
          @questions-translated="onQuestionsTranslated"
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
            <UploadingDots text="Processing" />
          </div>
          <ChatMessageItem
            v-for="(msg, index) in displayedMessages"
            :key="msg.id || index"
            :ref="
              (el: any) => {
                if (index === 0) firstMessageRef = el
              }
            "
            :msg="msg"
            :asking="assistantPending"
            :conversation-id="conversationId"
            :storage-conversation-id="storageConversationId"
            :is-welcome="isUploadMessage(index)"
            :is-first-message="index === 0 && msg.role === 'assistant' && !msg.isParentMessage"
            :can-upload="canUpload"
            :files="uploadFilesForMessage(index)"
            :suggested-questions="canReply ? suggestedQuestionsForMessage(index) : []"
            :conversation-name="conversationTitle"
            :file-name="primaryFileName"
            :is-thread="isThread"
            :no-animation="index < initialMessageCount"
            :is-translating="isTranslating"
            @select-question="question = $event; submitQuestion()"
            @upload-files="handleUploadFiles"
            @trigger-upload="triggerUploadOnFirstMessage"
            @view-threads="viewThreads"
          />
        </div>

        <div v-if="roleLoaded && canReply" class="chat-input-bar">
          <textarea
            ref="questionInput"
            v-model="question"
            class="chat-textarea"
            :placeholder="isViewer ? 'Reply to start your own thread...' : 'Ask a question...'"
            rows="1"
            @input="autoResize"
            @keydown.enter.exact.prevent="submitQuestion"
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
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch, nextTick } from 'vue'
import { AxiosError } from 'axios'
import {
  askQuestion,
  generateImage,
  getConversation,
  uploadMoreFiles,
  createConversationThread,
  saveConversationToken,
  extractError,
  type ConversationStatus,
  type ChatMessage,
} from '../api'
import { cleanFileName } from '../utils/text'
import { getUserId } from '../utils/fingerprint'
import { getData, setData } from '../utils/localData'
import { useRouter } from 'vue-router'
import ConversationHeader from '../components/ConversationHeader.vue'
import ChatMessageItem from '../components/ChatMessage.vue'
import ErrorDetail from '../components/ErrorDetail.vue'
import LanguageToggle from '../components/LanguageToggle.vue'
import UploadingDots from '../components/UploadingDots.vue'
import { useTextSelectionSpeech } from '../composables/useTextSelectionSpeech'
import { useAutoRead } from '../composables/useAutoRead'
import { useConversationEvents, stepLabel } from '../composables/useConversationEvents'
import { IMAGE_GEN_REGEX } from '../utils/markdown'

const props = defineProps<{ conversationId: string }>()

const conversationId = props.conversationId
const question = ref('')
const asking = ref(false)
const questionInput = ref<HTMLTextAreaElement | null>(null)
const chatContainer = ref<HTMLDivElement | null>(null)

const currentLanguage = ref('')
const isTranslating = ref(false)

const status = ref<ConversationStatus>({
  conversationId,
  displayName: null,
  status: 'processing',
  role: 'viewer',
  parentMessageId: null,
  parentConversationId: null,
  files: [],
  messages: [],
  suggestedQuestions: [],
  accessRequests: [],
})
const messages = ref<ChatMessage[]>([])
const initialMessageCount = ref(Infinity)
const hasLocalError = ref(false)

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

const displayedMessages = computed<ChatMessage[]>(() => {
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
} = useAutoRead(messages, asking, welcomeMessageContent)

// SSE: real-time processing events (welcome_message, complete)
const {
  processingStep,
  parsedPages,
  totalPages,
  connect: connectSSE,
  disconnect: disconnectSSE,
  onWelcome,
  onComplete: onSSEComplete,
} = useConversationEvents(conversationId)

onWelcome(() => loadConversation())
onSSEComplete(() => loadConversation())

const processingStepLabel = computed(() => stepLabel(processingStep.value))

const headerRef = ref<InstanceType<typeof ConversationHeader> | null>(null)
const firstMessageRef = ref<InstanceType<typeof ChatMessageItem> | null>(null)
const loaded = ref(false)
const routerInstance = useRouter()

const isThread = computed(() => !!status.value.parentMessageId)

// For threads, files live under the parent conversation's storage namespace
const storageConversationId = computed(() => status.value.storageNamespace || conversationId)

// Translation state
const originalMessages = ref<Map<number, string>>(new Map())
const originalSuggestedQuestions = ref<Map<string, string>>(new Map()) // translated → original

// Collect all suggested questions for translation (status-level + per-message)
const allSuggestedQuestions = computed(() => {
  const qs = [...status.value.suggestedQuestions]
  for (const msg of messages.value) {
    if (msg.suggestedQuestions?.length) {
      for (const q of msg.suggestedQuestions) {
        if (!qs.includes(q)) qs.push(q)
      }
    }
  }
  return qs
})

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
}

function onQuestionsTranslated(translated: string[]) {
  const all = allSuggestedQuestions.value
  // Build original→translated and translated→original maps
  const fwdMap = new Map<string, string>()
  all.forEach((q, i) => {
    if (translated[i] && translated[i] !== q) {
      fwdMap.set(q, translated[i])
      originalSuggestedQuestions.value.set(translated[i], q)
    }
  })
  // Apply to status-level
  status.value.suggestedQuestions = status.value.suggestedQuestions.map((q) => fwdMap.get(q) || q)
  // Apply to per-message
  for (const msg of messages.value) {
    if (msg.suggestedQuestions?.length) {
      msg.suggestedQuestions = msg.suggestedQuestions.map((q) => fwdMap.get(q) || q)
    }
  }
}

function onRestored(newTranslations: Map<number, string>) {
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

  // Restore suggested questions
  if (originalSuggestedQuestions.value.size) {
    const revMap = originalSuggestedQuestions.value // translated → original
    status.value.suggestedQuestions = status.value.suggestedQuestions.map((q) => revMap.get(q) || q)
    for (const msg of messages.value) {
      if (msg.suggestedQuestions?.length) {
        msg.suggestedQuestions = msg.suggestedQuestions.map((q) => revMap.get(q) || q)
      }
    }
    originalSuggestedQuestions.value.clear()
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

function isLastUploadMessage(index: number): boolean {
  if (!isUploadMessage(index)) return false
  // Check that no later message is also an upload message
  for (let i = index + 1; i < messages.value.length; i++) {
    if (isUploadMessage(i)) return false
  }
  return true
}

function suggestedQuestionsForMessage(index: number): string[] | undefined {
  const msg = messages.value[index]
  // Non-upload messages with explicit suggested questions (e.g. viewer hello message)
  if (!isUploadMessage(index) && msg?.suggestedQuestions?.length) {
    return msg.suggestedQuestions
  }
  if (!isUploadMessage(index)) return undefined
  // Use per-message suggested questions if available
  if (msg.suggestedQuestions?.length) return msg.suggestedQuestions
  // Legacy fallback: show all questions on last upload message only
  // Skip during processing to avoid flashing old questions on the wrong message
  if (status.value.status === 'processing') return undefined
  if (isLastUploadMessage(index) && status.value.suggestedQuestions.length) {
    return status.value.suggestedQuestions
  }
  return undefined
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

async function loadConversation() {
  const response = await getConversation(conversationId)
  status.value = response

  // Viewer mode: show the original welcome message + a virtual hello message
  const viewerMode =
    response.role === 'viewer' && !response.parentMessageId && !response.parentConversationId
  if (viewerMode) {
    if (messages.value.length === 0) {
      const name = response.displayName || 'this topic'
      const serverMessages = response.messages || []
      const firstWelcome = serverMessages.find((m: ChatMessage) => m.role === 'assistant')

      const viewerMessages: ChatMessage[] = []

      // 1st message: original welcome message (same as owner sees, with file previews)
      if (firstWelcome) {
        viewerMessages.push({
          ...firstWelcome,
          suggestedQuestions: undefined, // questions go on the hello message
        })
      }

      // 2nd message: virtual hello message with suggested questions
      viewerMessages.push({
        role: 'assistant',
        content: `Hi! How can I help you with **${name}**?`,
        suggestedQuestions: response.suggestedQuestions.length
          ? response.suggestedQuestions
          : undefined,
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
    if (originalMessages.value.size > 0) {
      // In translated mode: preserve translated content for existing messages
      // Update originals with fresh server data
      originalMessages.value.forEach((_, i) => {
        if (serverMessages[i]) {
          originalMessages.value.set(i, serverMessages[i].content)
        }
      })
      // Append any new messages from server (not yet translated)
      for (let i = messages.value.length; i < serverMessages.length; i++) {
        messages.value.push(serverMessages[i])
      }
    } else if (serverMessages.length !== messages.value.length) {
      messages.value = serverMessages
    } else {
      // Sync per-message metadata that may arrive after initial message creation
      // (e.g. suggestedQuestions generated after upload processing finishes)
      for (let i = 0; i < serverMessages.length; i++) {
        const srv = serverMessages[i]
        const local = messages.value[i]
        if (srv.suggestedQuestions?.length && !local.suggestedQuestions?.length) {
          local.suggestedQuestions = srv.suggestedQuestions
        }
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
      const names = ((err.response.data as Record<string, unknown>)?.duplicates as string[] || []).join(', ')
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

function scrollToBottom(smooth = false) {
  if (!chatContainer.value) return
  const container = chatContainer.value
  // Find the last message element
  const messageEls = container.querySelectorAll('.message')
  const lastMsg = messageEls[messageEls.length - 1] as HTMLElement | undefined
  if (lastMsg) {
    // Scroll so the top of the last message aligns with the top of the container.
    // If the message is shorter than the viewport, scrolling to its top is enough.
    const msgTop = lastMsg.offsetTop - container.offsetTop
    const maxScroll = container.scrollHeight - container.clientHeight
    container.scrollTo({
      top: Math.min(msgTop, maxScroll),
      behavior: smooth ? 'smooth' : 'instant',
    })
  } else {
    container.scrollTo({
      top: container.scrollHeight,
      behavior: smooth ? 'smooth' : 'instant',
    })
  }
}

async function ask() {
  if (!question.value.trim()) return
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
  question.value = ''
  messages.value.push({ role: 'user', content: currentQuestion })

  messages.value.push({ role: 'assistant', content: '' })
  // Use the reactive proxy so Vue detects content updates immediately
  const reactiveMsg = messages.value[messages.value.length - 1]

  const TIMEOUT_MS = 120_000 // 2 minutes max for an answer
  try {
    const timeout = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error('Request timed out')), TIMEOUT_MS),
    )
    const isImageGen = IMAGE_GEN_REGEX.test(currentQuestion)
    if (isImageGen) {
      reactiveMsg.generatingImage = true
    }
    const response = await Promise.race([
      isImageGen
        ? generateImage(conversationId, currentQuestion, getUserId() || undefined)
        : askQuestion(conversationId, currentQuestion, getUserId() || undefined),
      timeout,
    ])
    reactiveMsg.content = response.answer
    reactiveMsg.citations = response.citations
    if (response.assistantMessageId) reactiveMsg.id = response.assistantMessageId
    // Also assign user message id
    const userMsg = messages.value[messages.value.length - 2]
    if (response.userMessageId && userMsg?.role === 'user') userMsg.id = response.userMessageId
    await nextTick()
    scrollToBottom(true)
    await loadConversation()
  } catch (err: unknown) {
    const { message, raw } = extractError(err)
    reactiveMsg.content = `⚠️ Error: ${message}\n\n<details><summary>Show details</summary>\n\n\`\`\`\n${raw}\n\`\`\`\n</details>`
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
}

function autoResize(e: Event) {
  const el = e.target as HTMLTextAreaElement
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
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
function onChatScroll() {
  if (scrollSaveTimer) clearTimeout(scrollSaveTimer)
  scrollSaveTimer = setTimeout(saveScrollPosition, 300)
}

let prevMessageCount = 0
const conversationReady = ref(false)

// Auto-read welcome message when conversation first becomes ready
let welcomeReadTriggered = false
watch(
  () => status.value.status,
  (newStatus) => {
    if (newStatus === 'ready' && !welcomeReadTriggered && messages.value.length > 0) {
      welcomeReadTriggered = true
      readWelcomeIfEnabled()
    }
  },
)

watch(
  () => messages.value.length,
  async (newLen) => {
    if (conversationReady.value && newLen > prevMessageCount) {
      await nextTick()
      setTimeout(() => scrollToBottom(), 0)
    }
    prevMessageCount = newLen
  },
)

let intervalHandle: number | undefined

onMounted(async () => {
  await loadConversation()
  loaded.value = true
  roleLoaded.value = true
  await nextTick()
  // Restore saved scroll position, or fall back to scrolling to bottom
  if (!restoreScrollPosition()) {
    scrollToBottom()
  }
  prevMessageCount = messages.value.length
  conversationReady.value = true

  // Listen for scroll events to persist position
  chatContainer.value?.addEventListener('scroll', onChatScroll, { passive: true })

  // Connect SSE for real-time processing events while conversation is being indexed
  if (status.value.status === 'processing') {
    connectSSE()
  }

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

  intervalHandle = window.setInterval(async () => {
    await loadConversation()
  }, 1000)
})

onUnmounted(() => {
  if (intervalHandle !== undefined) {
    clearInterval(intervalHandle)
  }
  disconnectSSE()
  chatContainer.value?.removeEventListener('scroll', onChatScroll)
  if (scrollSaveTimer) clearTimeout(scrollSaveTimer)
  cleanupAutoRead()
})
</script>
