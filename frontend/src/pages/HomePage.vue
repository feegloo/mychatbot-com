<template>
  <div class="page home-page">
    <!-- Logo + tagline -->
    <div class="home-hero">
      <img src="/logo.svg" alt="chatrag.app" class="home-logo" />
      <p class="home-subtitle">
        Upload your files securely 🔒 and let learning AI tell you what’s inside.<br /><br/> Ask prompt to <strong> AI Agent chatbot</strong>, research, use semantic search & RAG, share answers<br />
        <span style="font-size: 12px; padding-top: 6px"
          >Generate image 🎨 book chapter 📖 poem 📜 diagnosis 🔬 quiz 🧠 quote 💡 PDF 📄 mermaid diagram 🧩 recipe 🍝 checklist ✅ and more!</span
        >
      </p>
    </div>

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
          <p><strong>Click to upload or drag & drop</strong></p>
          <p class="dropzone-hint">PDF, images, .doc, other text files</p>
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
        :asking="asking"
        :conversation-id="conversationId || ''"
        :is-welcome="false"
        :is-first-message="false"
        :can-upload="false"
        :files="undefined"
        :suggested-questions="undefined"
        @image-revealed="(success: boolean) => success && scrollToBottom(true)"
      />
    </div>

    <!-- Chat input bar (always visible) -->
    <div class="chat-input-bar home-chat-input">
      <textarea
        ref="questionInput"
        v-model="question"
        class="chat-textarea"
        placeholder="Ask a question ..."
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
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  uploadFiles as apiUploadFiles,
  uploadUrl as apiUploadUrl,
  createConversation,
  askQuestion,
  generateImage,
  announceImage,
  saveConversationToken,
  extractError,
  type ChatMessage,
} from '../api'
import ChatMessageItem from '../components/ChatMessage.vue'
import ErrorDetail from '../components/ErrorDetail.vue'
import UploadingDots from '../components/UploadingDots.vue'
import { IMAGE_GEN_REGEX } from '../utils/markdown'

onMounted(() => {
  document.title = 'chatrag.app'
})

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
  if (videoFiles.length) uploadError.value = { message: 'Video files are not supported.' }
  if (uploadFilesArr.value.length) submitUpload()
}

function onDrop(event: DragEvent) {
  dragover.value = false
  const allFiles = Array.from(event.dataTransfer?.files || [])
  const videoFiles = allFiles.filter((f) => f.type.startsWith('video/'))
  uploadFilesArr.value = allFiles.filter((f) => !f.type.startsWith('video/'))
  if (videoFiles.length) uploadError.value = { message: 'Video files are not supported.' }
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
  } catch (err: any) {
    const { message, raw } = extractError(err)
    const status = err?.response?.status
    if (status === 413) {
      uploadError.value = {
        message: 'File too large. Maximum upload size is ~30 MB per file.',
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
  } catch (err: any) {
    const { message, raw } = extractError(err)
    uploadError.value = { message: message || 'Failed to load URL', raw }
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

  asking.value = true
  messages.value.push({ role: 'user', content: currentQuestion })
  messages.value.push({ role: 'assistant', content: '' })
  const reactiveMsg = messages.value[messages.value.length - 1]

  await nextTick()
  scrollToBottom()

  try {
    const convId = await ensureConversation()

    const TIMEOUT_MS = 120_000
    const timeout = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error('Request timed out')), TIMEOUT_MS),
    )
    const isImageGen = IMAGE_GEN_REGEX.test(currentQuestion)
    if (isImageGen) {
      reactiveMsg.generatingImage = true
      announceImage(convId, currentQuestion)
        .then(({ announcement }) => {
          if (announcement && reactiveMsg.generatingImage) {
            reactiveMsg.imageAnnouncement = announcement
          }
        })
        .catch(() => {})
    }
    const response = await Promise.race([
      isImageGen ? generateImage(convId, currentQuestion) : askQuestion(convId, currentQuestion),
      timeout,
    ])
    reactiveMsg.content = response.answer
    reactiveMsg.citations = response.citations
    if (response.assistantMessageId) reactiveMsg.id = response.assistantMessageId
    const userMsg = messages.value[messages.value.length - 2]
    if (response.userMessageId && userMsg?.role === 'user') userMsg.id = response.userMessageId
    await nextTick()
    scrollToBottom(true)
  } catch (err: any) {
    reactiveMsg.generatingImage = false
    if (IMAGE_GEN_REGEX.test(currentQuestion)) {
      reactiveMsg.content = 'Sorry, there was an error during generating image. Try again.'
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
}

.home-hero {
  text-align: center;
  margin-bottom: 32px;
  flex-shrink: 0;
}

.home-logo {
  height: 52px;
  width: auto;
  display: block;
  margin: -10px auto 16px;
  filter: drop-shadow(0 0 24px rgba(167, 139, 250, 0.3));
}

.home-subtitle {
  color: #64748b;
  margin: 0;
  font-size: 15px;
  line-height: 1.5;
}

.upload-section {
  width: 100%;
  max-width: 560px;
  position: relative;
  margin-bottom: 24px;
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
  padding: 48px 36px;
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
  margin-top: 80px;
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
    padding: 24px 16px;
  }

  .home-logo {
    height: 40px;
  }

  .upload-dropzone {
    padding: 32px 20px;
  }
}
</style>
