<template>
  <div class="page home-page">
    <!-- Home-page-only language toggle (independent of conversation
         translation handled by LanguageToggle.vue). -->
    <HomeLanguageToggle v-if="showUpload" />

    <!-- Logo + tagline -->
    <HomeHero v-if="showUpload" />

    <!-- Upload section (fades out after upload starts processing) -->
    <Transition :name="skipUploadTransition ? '' : 'fade-upload'">
      <div v-if="showUpload" class="upload-section">
        <div
          class="dropzone upload-dropzone"
          :class="{ dragover }"
          style="cursor: pointer"
          @dragover.prevent="dragover = true"
          @dragleave.prevent="dragover = false"
          @drop.prevent="onDrop"
          @click="openFilePicker"
        >
          <div class="dropzone-icon">
            <svg
              width="40"
              height="40"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
          </div>
          <p class="dropzone-heading">{{ t.dropzoneHeading }}</p>
          <p class="dropzone-title">
            <strong>{{ t.dropzoneTitle }}</strong>
          </p>
          <p class="dropzone-hint">{{ t.dropzoneHint }}</p>
          <input
            ref="inputRef"
            type="file"
            multiple
            style="display: none"
            @change="onInputChange"
          />
        </div>

        <div class="upload-status-area">
          <div v-if="uploadFiles.length" class="file-list" style="margin-top: 16px">
            <div v-for="file in uploadFiles" :key="file.name" class="file-pill">
              {{ file.name }} - {{ (file.size / 1024 / 1024).toFixed(1) }} MB
            </div>
          </div>
          <p v-if="uploading" style="margin-top: 12px; color: #a78bfa; text-align: center">
            <UploadingDots />
          </p>
          <ErrorDetail
            v-if="uploadError.message"
            :message="uploadError.message"
            :raw="uploadError.raw"
          />
        </div>
      </div>
    </Transition>

    <!-- Chat messages (appears after first question) -->
    <div v-if="messages.length" ref="chatContainer" class="chat-log home-chat-log">
      <ChatMessageItem
        v-for="(msg, index) in messages"
        :key="index"
        :msg="msg"
        :all-messages="messages"
        :asking="asking"
        :conversation-id="conversationId || ''"
        :is-welcome="false"
        :is-first-message="false"
        :can-upload="false"
        :files="undefined"
        @image-revealed="(success) => success && scrollToBottom(true)"
      />
    </div>

    <!-- Chat input bar (always visible) -->
    <div class="chat-input-bar home-chat-input">
      <textarea
        ref="questionInput"
        v-model="question"
        class="chat-textarea"
        :placeholder="t.askPlaceholder"
        rows="1"
        @input="autoResize"
        @keydown.enter.exact.prevent="submitQuestion"
        @paste="onPasteFile"
      ></textarea>
      <button class="send-btn" :disabled="asking || !question.trim()" @click="submitQuestion">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
          <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import {
  uploadFiles as apiUploadFiles,
  uploadUrl as apiUploadUrl,
  createConversation,
  askQuestion,
  saveConversationToken,
  extractError,
  httpStatus,
  type ChatMessage,
} from '../api'
import { runImageGenStream } from '../composables/useImageGenStream'
import ChatMessageItem from '../components/ChatMessage.vue'
import ErrorDetail from '../components/ErrorDetail.vue'
import HomeHero from '../components/HomeHero.vue'
import HomeLanguageToggle from '../components/HomeLanguageToggle.vue'
import UploadingDots from '../components/UploadingDots.vue'
import { homeT } from '../i18n/homeLocale'
import { IMAGE_GEN_REGEX } from '../utils/markdown'
import { extractPastedFiles } from '../composables/useFilePaste'

const t = homeT

const router = useRouter()

// Upload state
const uploadFilesArr = ref<File[]>([])
const uploadFiles = uploadFilesArr
const dragover = ref(false)
const uploading = ref(false)
const uploadError = ref<{ message: string; raw?: string }>({ message: '' })
const inputRef = ref<HTMLInputElement | null>(null)
const showUpload = ref(true)
const skipUploadTransition = ref(false)

// Chat state
const question = ref('')
const asking = ref(false)
const messages = ref<ChatMessage[]>([])
const conversationId = ref<string | null>(null)
const ownerPassword = ref<string | null>(null)
const questionInput = ref<HTMLTextAreaElement | null>(null)
const chatContainer = ref<HTMLDivElement | null>(null)

function openFilePicker() {
  inputRef.value?.click()
}

function onInputChange(event: Event) {
  const target = event.target as HTMLInputElement
  const allFiles = Array.from(target.files || [])
  const videoFiles = allFiles.filter((f) => f.type.startsWith('video/'))
  uploadFilesArr.value = allFiles.filter((f) => !f.type.startsWith('video/'))
  if (videoFiles.length) uploadError.value = { message: t.value.videoNotSupported }
  if (uploadFilesArr.value.length) submitUpload()
}

function onDrop(event: DragEvent) {
  dragover.value = false
  const allFiles = Array.from(event.dataTransfer?.files || [])
  const videoFiles = allFiles.filter((f) => f.type.startsWith('video/'))
  uploadFilesArr.value = allFiles.filter((f) => !f.type.startsWith('video/'))
  if (videoFiles.length) uploadError.value = { message: t.value.videoNotSupported }
  if (uploadFilesArr.value.length) submitUpload()
}

async function submitUpload() {
  uploading.value = true
  uploadError.value = { message: '' }

  try {
    const data = await apiUploadFiles(uploadFilesArr.value)
    if (data.ownerPassword) {
      saveConversationToken(data.conversationId, data.ownerPassword)
      ownerPassword.value = data.ownerPassword
    }
    conversationId.value = data.conversationId
    // Fade out upload section
    showUpload.value = false
    // Navigate to conversation page
    router.push(data.url)
  } catch (err: unknown) {
    const { message, raw } = extractError(err)
    const status = httpStatus(err)
    if (status === 413) {
      uploadError.value = {
        message: t.value.fileTooLarge,
        raw,
      }
    } else {
      uploadError.value = { message, raw }
    }
  } finally {
    uploading.value = false
  }
}

async function ensureConversation(): Promise<string> {
  if (conversationId.value) return conversationId.value

  const data = await createConversation()
  conversationId.value = data.conversationId
  if (data.ownerPassword) {
    saveConversationToken(data.conversationId, data.ownerPassword)
    ownerPassword.value = data.ownerPassword
  }
  // Update URL in-place to conversation path
  window.history.replaceState({}, '', data.url)
  window.dispatchEvent(new CustomEvent('conversation-updated'))
  return data.conversationId
}

function scrollToBottom(smooth = false) {
  if (chatContainer.value) {
    chatContainer.value.scrollTo({
      top: chatContainer.value.scrollHeight,
      behavior: smooth ? 'smooth' : 'instant',
    })
  }
}

const URL_REGEX = /^https?:\/\/[^\s]+$/i

function isUrl(text: string): boolean {
  return URL_REGEX.test(text.trim())
}

async function submitUrlUpload(url: string) {
  uploading.value = true
  uploadError.value = { message: '' }

  try {
    const data = await apiUploadUrl(url.trim())
    if (data.ownerPassword) {
      saveConversationToken(data.conversationId, data.ownerPassword)
      ownerPassword.value = data.ownerPassword
    }
    conversationId.value = data.conversationId
    showUpload.value = false
    router.push(data.url)
  } catch (err: unknown) {
    const { message, raw } = extractError(err)
    uploadError.value = { message: message || t.value.urlLoadFailed, raw }
  } finally {
    uploading.value = false
  }
}

async function submitQuestion() {
  if (asking.value || !question.value.trim()) return

  // If no conversation yet and the input looks like a URL, treat as URL upload
  if (!conversationId.value && isUrl(question.value)) {
    const url = question.value.trim()
    question.value = ''
    if (questionInput.value) questionInput.value.style.height = 'auto'
    await submitUrlUpload(url)
    return
  }

  const currentQuestion = question.value
  question.value = ''
  if (questionInput.value) questionInput.value.style.height = 'auto'

  // First question from home should immediately transition to full
  // conversation view instead of rendering chat inside the home hero layout.
  if (!conversationId.value) {
    asking.value = true
    try {
      const data = await createConversation()
      conversationId.value = data.conversationId
      if (data.ownerPassword) {
        saveConversationToken(data.conversationId, data.ownerPassword)
        ownerPassword.value = data.ownerPassword
      }
      showUpload.value = false
      await router.push({ path: data.url, state: { pendingQuestion: currentQuestion } })
    } catch (err: unknown) {
      const { message, raw } = extractError(err)
      uploadError.value = { message, raw }
      question.value = currentQuestion
      if (questionInput.value) questionInput.value.style.height = 'auto'
    } finally {
      asking.value = false
    }
    return
  }

  asking.value = true
  messages.value.push({ role: 'user', content: currentQuestion })
  messages.value.push({ role: 'assistant', content: '' })
  const reactiveMsg = messages.value[messages.value.length - 1]

  await nextTick()
  scrollToBottom()

  try {
    const convId = await ensureConversation()
    const promptLanguage = navigator.language.split('-')[0]

    const TIMEOUT_MS = 120_000
    const timeout = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error('Request timed out')), TIMEOUT_MS),
    )
    const isImageGen = IMAGE_GEN_REGEX.test(currentQuestion)
    const response = isImageGen
      ? await runImageGenStream({
          conversationId: convId,
          question: currentQuestion,
          reactiveMsg,
          timeoutMs: TIMEOUT_MS,
          useUserId: false,
          language: promptLanguage,
          onAnnouncement: () => {
            nextTick(() => scrollToBottom(true))
          },
        })
      : await Promise.race([askQuestion(convId, currentQuestion, undefined, promptLanguage), timeout])
    reactiveMsg.generatingImage = false
    reactiveMsg.imagePartialDataUrl = undefined
    reactiveMsg.imageDetailedPrompt = undefined
    reactiveMsg.content = response.answer
    reactiveMsg.citations = response.citations
    if (response.assistantMessageId) reactiveMsg.id = response.assistantMessageId
    const userMsg = messages.value[messages.value.length - 2]
    if (response.userMessageId && userMsg?.role === 'user') userMsg.id = response.userMessageId
    await nextTick()
    scrollToBottom(true)
  } catch (err: unknown) {
    reactiveMsg.generatingImage = false
    reactiveMsg.imageDetailedPrompt = undefined
    if (IMAGE_GEN_REGEX.test(currentQuestion)) {
      const openaiMessage = (err as any)?.openaiMessage
      reactiveMsg.content = openaiMessage
        ? `${t.value.imageGenError}\n\n> ${openaiMessage}`
        : t.value.imageGenError
    } else {
      const { message, raw } = extractError(err)
      reactiveMsg.content = `⚠️ Error: ${message}\n\n<details><summary>Show details</summary>\n\n\`\`\`\n${raw}\n\`\`\`\n</details>`
    }
  } finally {
    asking.value = false
  }
}

function autoResize(e: Event) {
  const el = e.target as HTMLTextAreaElement
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}

function onPasteFile(event: ClipboardEvent) {
  const files = extractPastedFiles(event)
  if (files.length === 0) return
  event.preventDefault()
  uploadFilesArr.value = files
  submitUpload()
}
</script>

<style scoped>
.home-page {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 0 32px 24px;
  overflow-y: auto;
  gap: 0;
  /* Anchor for the absolutely-positioned HomeLanguageToggle. */
  position: relative;
}

.upload-section {
  width: 100%;
  max-width: 560px;
  position: relative;
  flex-shrink: 0;
}

.upload-status-area {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
}

.upload-heading {
  font-size: 1.1rem;
  margin: 0 0 14px;
  text-align: center;
}

.upload-dropzone {
  padding: 36px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.dropzone-icon {
  color: #7c3aed;
  margin-bottom: 8px;
  opacity: 0.7;
  transition:
    opacity 0.25s ease,
    transform 0.25s ease;
}

.upload-dropzone p {
  margin: 4px 0;
}

.dropzone-heading {
  font-size: 28px;
  font-weight: 700;
  color: #fff;
  margin-bottom: 2px;
}

.dropzone-hint {
  color: #64748b;
  font-size: 13px;
}

.home-chat-log {
  flex: 1;
  width: 100%;
  max-width: 800px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-right: 8px;
  margin-bottom: 16px;
}

.home-chat-input {
  width: 100%;
  max-width: 700px;
  flex-shrink: 0;
  margin-top: 100px;
}

/* Fade transition for upload section */
.fade-upload-enter-active,
.fade-upload-leave-active {
  transition:
    opacity 0.4s ease,
    transform 0.4s ease;
}

.fade-upload-enter-from {
  opacity: 0;
  transform: translateY(-10px);
}

.fade-upload-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

@media (max-width: 768px) {
  .home-page {
    padding: 10px 16px 120px;
    justify-content: flex-start;
  }

  .upload-dropzone {
    padding: 32px 20px;
  }

  .dropzone-title {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }

  .home-chat-input {
    position: fixed;
    bottom: calc(30px + env(safe-area-inset-bottom, 0px));
    left: 16px;
    right: 16px;
    width: auto;
    max-width: none;
    margin-top: 0;
    z-index: 10;
  }
}
</style>
