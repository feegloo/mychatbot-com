<template>
  <div class="page" :class="{ 'shared-conversation-view': isViewer }">
    <ConversationHeader
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
                if (index === 0) firstMessageRef = el as InstanceType<typeof ChatMessageItem> | null
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
            :max-visible-actions="index === 0 ? 5 : 3"
            :conversation-name="conversationTitle"
            :file-name="primaryFileName"
            :is-thread="isThread"
            :no-animation="index < initialMessageCount"
            :animate="index >= initialMessageCount && !!msg.id && !animatedMessageIds.has(msg.id)"
            :is-translating="isTranslating"
            @select-question="
              question = $event;
              submitQuestion();
            "
            @upload-files="handleUploadFiles"
            @trigger-upload="triggerUploadOnFirstMessage"
            @view-threads="viewThreads"
            @image-revealed="(success) => success && scrollToBottom(true, true)"
            @message-animated="onMessageAnimated(msg.id)"
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
import { computed, onMounted, onUnmounted, onActivated, onDeactivated, ref, watch, nextTick } from 'vue'
import { AxiosError } from 'axios'
import {
  askQuestion,
  getConversation,
  uploadMoreFiles,
  addUrlToConversation,
  createConversationThread,
  saveConversationToken,
  extractError,
  type ConversationStatus,
  type ChatMessage,
} from '../api'
import { runImageGenStream } from '../composables/useImageGenStream'
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
import { useSSE } from '../composables/useGlobalSSE'
import { IMAGE_GEN_REGEX } from '../utils/markdown'

type ProcessingStep = 'generating_welcome' | 'indexing_pages' | ''
const STEP_LABELS: Record<ProcessingStep, string> = {
  generating_welcome: 'Processing',
  indexing_pages: 'Indexing pages for Q&A…',
  '': '',
}
function stepLabel(step: ProcessingStep): string {
  return STEP_LABELS[step] || ''
}
import {newContent} from '../composables/newContent'
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
  accessRequests: [],
})
const messages = ref<MessageWithRenderKey<ChatMessage>[]>([])
const initialMessageCount = ref(Infinity)
const hasLocalError = ref(false)

// Tracks which assistant message IDs have already had their word-reveal
// animation played. Cleared only on full page navigation. Using IDs (not
// indices) so the set stays correct after array replacements on reload.
const animatedMessageIds = ref(new Set<string>())

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
  }
})

const processingStepLabel = computed(() => stepLabel(processingStep.value))

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
const loaded = ref(false)
const routerInstance = useRouter()

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

function scrollToBottom(smooth = false, toEnd = false) {
  if (!chatContainer.value) return
  const container = chatContainer.value
  // When `toEnd` is true, scroll all the way to the bottom — used when the
  // last message's size can grow after mount (e.g. a generated image finishes
  // loading), so aligning to the top of the message would leave it off-screen.
  if (toEnd) {
    container.scrollTo({
      top: container.scrollHeight,
      behavior: smooth ? 'smooth' : 'instant',
    })
    return
  }
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
  question.value = ''
  const optimisticUserMessage: MessageWithRenderKey<ChatMessage> = {
    role: 'user',
    content: currentQuestion,
  }
  messages.value.push(
    attachRenderKey(
      optimisticUserMessage,
      nextMessageRenderKey('local-user'),
    ),
  )

  const optimisticAssistantMessage: MessageWithRenderKey<ChatMessage> = {
    role: 'assistant',
    content: '',
  }
  messages.value.push(
    attachRenderKey(
      optimisticAssistantMessage,
      nextMessageRenderKey('local-assistant'),
    ),
  )
  // Use the reactive proxy so Vue detects content updates immediately
  const reactiveMsg = messages.value[messages.value.length - 1]

  const TIMEOUT_MS = 120_000 // 2 minutes max for an answer
  try {
    const timeout = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error('Request timed out')), TIMEOUT_MS),
    )
    const isImageGen = IMAGE_GEN_REGEX.test(currentQuestion)
    const response = isImageGen
      ? await runImageGenStream({
          conversationId,
          question: currentQuestion,
          reactiveMsg,
          timeoutMs: TIMEOUT_MS,
        })
      : await Promise.race([
          askQuestion(conversationId, currentQuestion, getUserId() || undefined),
          timeout,
        ])
    reactiveMsg.generatingImage = false
    reactiveMsg.imagePartialDataUrl = undefined
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
    reactiveMsg.generatingImage = false
    if (IMAGE_GEN_REGEX.test(currentQuestion)) {
      reactiveMsg.content = 'Sorry, there was an error during generating image. Try again.'
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

// Auto-read welcome message only for fresh conversations (no prior user messages)
let welcomeReadTriggered = false
watch(
  () => status.value.status,
  (newStatus) => {
    const hasUserMessages = messages.value.some((m) => m.role === 'user')
    if (newStatus === 'ready' && !welcomeReadTriggered && messages.value.length > 0 && !hasUserMessages) {
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
      setTimeout(() => scrollToBottom(true), 0)
    }
    prevMessageCount = newLen
  },
)

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
})

onDeactivated(() => {
  saveScrollPosition()
  if (scrollSaveTimer) {
    clearTimeout(scrollSaveTimer)
    scrollSaveTimer = undefined
  }
})
</script>
