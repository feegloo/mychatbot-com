<template>
  <div class="embed-page" :class="{ 'embed-page--error': !!fatalError }">
    <!-- Fatal error (invalid/missing conversation) -->
    <div v-if="fatalError" class="embed-error">
      <div class="embed-error-icon">⚠️</div>
      <div class="embed-error-title">Unable to load chatbot</div>
      <div class="embed-error-detail">{{ fatalError }}</div>
    </div>

    <!-- Loading state -->
    <div v-else-if="!loaded" class="embed-loading">
      <div class="embed-spinner"></div>
      <div class="embed-loading-text">Loading conversation…</div>
    </div>

    <!-- Chat interface -->
    <template v-else>
      <div class="embed-header">
        <div class="embed-header-title">{{ conversationTitle }}</div>
        <div v-if="status.status === 'processing'" class="embed-header-badge">Processing…</div>
        <a
          class="embed-header-link"
          :href="fullConversationUrl"
          target="_blank"
          rel="noopener"
          title="Open in chatrag.app"
        >
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
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
            <polyline points="15 3 21 3 21 9" />
            <line x1="10" y1="14" x2="21" y2="3" />
          </svg>
        </a>
      </div>

      <div ref="chatContainer" class="embed-chat-log">
        <ChatMessageItem
          v-for="(msg, index) in displayedMessages"
          :key="msg.id || index"
          :msg="msg"
          :asking="assistantPending"
          :conversation-id="conversationId"
          :is-welcome="isUploadMessage(index)"
          :is-first-message="index === 0 && msg.role === 'assistant'"
          :can-upload="false"
          :suggested-questions="suggestedQuestionsForMessage(index)"
          :no-animation="index < initialMessageCount"
          @select-question="question = $event; submitQuestion()"
        />
      </div>

      <div class="embed-input-bar">
        <textarea
          ref="questionInput"
          v-model="question"
          class="embed-textarea"
          placeholder="Ask a question..."
          rows="1"
          @input="autoResize"
          @keydown.enter.exact.prevent="submitQuestion"
        ></textarea>
        <button
          class="embed-send-btn"
          :disabled="asking || !question.trim() || status.status !== 'ready'"
          @click="submitQuestion"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
          </svg>
        </button>
      </div>

      <div class="embed-footer">
        Powered by <a href="https://chatrag.app" target="_blank" rel="noopener">chatrag.app</a>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch, watchEffect, nextTick } from 'vue'
import {
  askQuestion,
  generateImage,
  getConversation,
  type ConversationStatus,
  type ChatMessage,
} from '../api'
import { cleanFileName } from '../utils/text'
import ChatMessageItem from '../components/ChatMessage.vue'
import { useTextSelectionSpeech } from '../composables/useTextSelectionSpeech'
import { IMAGE_GEN_REGEX } from '../utils/markdown'

const props = defineProps<{ conversationId: string }>()

const conversationId = props.conversationId
const question = ref('')
const asking = ref(false)
const questionInput = ref<HTMLTextAreaElement | null>(null)
const chatContainer = ref<HTMLDivElement | null>(null)

const welcomeMessageContent = ref('')

const loaded = ref(false)
const fatalError = ref('')
const hasLocalError = ref(false)

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

useTextSelectionSpeech(chatContainer, undefined, welcomeMessageContent, messages)

const HOST = window.location.origin
const fullConversationUrl = computed(() => `${HOST}/c/${conversationId}`)

const conversationTitle = computed(() => {
  if (status.value.displayName) return status.value.displayName
  if (status.value.files.length) {
    return status.value.files.map((f) => cleanFileName(f.originalName)).join(', ')
  }
  return 'Chat'
})

function isUploadMessage(index: number): boolean {
  const msg = messages.value[index]
  if (msg?.role !== 'assistant') return false
  if (msg.uploadedFileNames?.length) return true
  return index === 0
}

// Welcome message content used as TTS tone instructions
watchEffect(() => {
  const idx = messages.value.findIndex((_, i) => isUploadMessage(i))
  welcomeMessageContent.value = idx >= 0 ? messages.value[idx].content : ''
})

function isLastUploadMessage(index: number): boolean {
  if (!isUploadMessage(index)) return false
  for (let i = index + 1; i < messages.value.length; i++) {
    if (isUploadMessage(i)) return false
  }
  return true
}

function suggestedQuestionsForMessage(index: number): string[] | undefined {
  if (!isUploadMessage(index)) return undefined
  const msg = messages.value[index]
  if (msg.suggestedQuestions?.length) return msg.suggestedQuestions
  if (status.value.status === 'processing') return undefined
  if (isLastUploadMessage(index) && status.value.suggestedQuestions.length) {
    return status.value.suggestedQuestions
  }
  return undefined
}

async function loadConversation() {
  try {
    const response = await getConversation(conversationId)
    status.value = response
    if (!asking.value && !hasLocalError.value) {
      messages.value = response.messages || []
      if (initialMessageCount.value === Infinity) {
        initialMessageCount.value = messages.value.length
      }
    }
  } catch (err: any) {
    if (!loaded.value) {
      const statusCode = err?.response?.status
      if (statusCode === 404) {
        fatalError.value = `Conversation "${conversationId}" not found. Please check the conversation ID.`
      } else if (statusCode === 403) {
        fatalError.value = 'Access denied. This conversation is not publicly available.'
      } else {
        fatalError.value = `Failed to load conversation: ${err?.message || 'Unknown error'}`
      }
      console.error(`[chatrag] Failed to load conversation "${conversationId}":`, err)
      notifyParent('error', { error: fatalError.value })
    }
  }
}

function scrollToBottom(smooth = false) {
  if (chatContainer.value) {
    chatContainer.value.scrollTo({
      top: chatContainer.value.scrollHeight,
      behavior: smooth ? 'smooth' : 'instant',
    })
  }
}

async function ask() {
  if (!question.value.trim()) return
  if (status.value.status !== 'ready') return

  asking.value = true
  hasLocalError.value = false
  const currentQuestion = question.value
  question.value = ''
  messages.value.push({ role: 'user', content: currentQuestion })
  messages.value.push({ role: 'assistant', content: '' })
  const reactiveMsg = messages.value[messages.value.length - 1]

  const TIMEOUT_MS = 120_000
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
        ? generateImage(conversationId, currentQuestion)
        : askQuestion(conversationId, currentQuestion),
      timeout,
    ])
    reactiveMsg.content = response.answer
    reactiveMsg.citations = response.citations
    if (response.assistantMessageId) reactiveMsg.id = response.assistantMessageId
    const userMsg = messages.value[messages.value.length - 2]
    if (response.userMessageId && userMsg?.role === 'user') userMsg.id = response.userMessageId
    await nextTick()
    scrollToBottom(true)
    await loadConversation()
  } catch (err: any) {
    const detail = err?.response?.data?.error || err?.message || 'Unknown error'
    reactiveMsg.content = `⚠️ Error: ${detail}`
    hasLocalError.value = true
    console.error(`[chatrag] Ask error:`, err)
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

/** Notify parent window (for widget postMessage communication) */
function notifyParent(type: string, data: Record<string, unknown> = {}) {
  try {
    if (window.parent !== window) {
      window.parent.postMessage({ source: 'chatrag-embed', type, conversationId, ...data }, '*')
    }
  } catch {
    // cross-origin — silently ignore
  }
}

let prevMessageCount = 0
watch(
  () => messages.value.length,
  async (newLen) => {
    if (newLen > prevMessageCount) {
      await nextTick()
      setTimeout(() => scrollToBottom(), 0)
    }
    prevMessageCount = newLen
  },
)

let intervalHandle: number | undefined

onMounted(async () => {
  if (!conversationId || conversationId.trim() === '') {
    fatalError.value = 'Missing conversation ID. Please provide a valid conversation ID.'
    console.error('[chatrag] No conversation ID provided.')
    notifyParent('error', { error: fatalError.value })
    return
  }

  await loadConversation()
  if (!fatalError.value) {
    loaded.value = true
    notifyParent('ready')
    await nextTick()
    setTimeout(() => scrollToBottom(), 100)

    intervalHandle = window.setInterval(async () => {
      await loadConversation()
    }, 2000)
  }
})

onUnmounted(() => {
  if (intervalHandle !== undefined) {
    clearInterval(intervalHandle)
  }
})
</script>

<style scoped>
.embed-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100%;
  background: #0b0f1a;
  color: #e2e8f0;
  font-family:
    'Lato',
    system-ui,
    -apple-system,
    sans-serif;
  overflow: hidden;
}

/* ── Error state ── */
.embed-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 32px;
  text-align: center;
  gap: 12px;
}
.embed-error-icon {
  font-size: 40px;
}
.embed-error-title {
  font-size: 16px;
  font-weight: 600;
  color: #f87171;
}
.embed-error-detail {
  font-size: 13px;
  color: #94a3b8;
  max-width: 320px;
}

/* ── Loading state ── */
.embed-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
}
.embed-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid rgba(167, 139, 250, 0.2);
  border-top-color: #a78bfa;
  border-radius: 50%;
  animation: embed-spin 0.7s linear infinite;
}
@keyframes embed-spin {
  to {
    transform: rotate(360deg);
  }
}
.embed-loading-text {
  font-size: 13px;
  color: #94a3b8;
}

/* ── Header ── */
.embed-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.02);
  min-height: 44px;
}
.embed-header-title {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #e2e8f0;
}
.embed-header-badge {
  font-size: 11px;
  color: #fbbf24;
  background: rgba(251, 191, 36, 0.1);
  padding: 2px 8px;
  border-radius: 10px;
}
.embed-header-link {
  color: #94a3b8;
  display: flex;
  align-items: center;
  padding: 4px;
  border-radius: 4px;
  transition: color 0.2s;
}
@media (hover: hover) {
  .embed-header-link:hover {
    color: #e2e8f0;
  }
}

/* ── Chat log ── */
.embed-chat-log {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 16px;
  padding-right: 8px;
}

/* ── Input bar ── */
.embed-input-bar {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 8px 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.02);
}
.embed-textarea {
  flex: 1;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  color: #e2e8f0;
  font-size: 14px;
  padding: 8px 12px;
  resize: none;
  outline: none;
  font-family: inherit;
  max-height: 120px;
  line-height: 1.4;
}
.embed-textarea:focus {
  border-color: rgba(167, 139, 250, 0.4);
}
.embed-textarea::placeholder {
  color: #64748b;
}
.embed-send-btn {
  background: #7c3aed;
  color: #fff;
  border: none;
  border-radius: 8px;
  width: 36px;
  height: 36px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s;
  flex-shrink: 0;
}
@media (hover: hover) {
  .embed-send-btn:hover:not(:disabled) {
    background: #6d28d9;
  }
}
.embed-send-btn:active:not(:disabled) {
  background: #6d28d9;
}
.embed-send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ── Footer ── */
.embed-footer {
  text-align: center;
  font-size: 11px;
  color: #475569;
  padding: 4px 8px 6px;
  border-top: 1px solid rgba(255, 255, 255, 0.04);
}
.embed-footer a {
  color: #7c3aed;
  text-decoration: none;
}
@media (hover: hover) {
  .embed-footer a:hover {
    text-decoration: underline;
  }
}
</style>
