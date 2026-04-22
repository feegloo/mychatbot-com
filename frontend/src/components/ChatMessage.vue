<template>
  <div ref="messageRootEl" class="message-row" :class="msg.role">
    <div class="message" :class="[msg.role, { 'welcome-message': isWelcome }]">
      <strong>{{ senderLabel }}</strong>
      <div v-if="msg.role === 'assistant' && msg.content" class="msg-actions">
        <AppButton
          v-if="isFirstMessage && canUpload"
          class="msg-action-btn"
          title="Upload more files"
          @click="uploadInput?.click()"
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
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
          Upload more files
        </AppButton>
        <AppButton
          class="msg-action-btn"
          :title="shareCopied ? 'Link copied!' : 'Share this answer'"
          @click="shareMessage"
        >
          <svg
            v-if="!shareCopied"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <circle cx="18" cy="5" r="3" />
            <circle cx="6" cy="12" r="3" />
            <circle cx="18" cy="19" r="3" />
            <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
            <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
          </svg>
          <svg
            v-else
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <polyline points="20 6 9 17 4 12" />
          </svg>
          {{ shareCopied ? 'Link copied!' : 'Share' }}
        </AppButton>
        <AppButton
          v-if="hasRichContent"
          class="msg-action-btn"
          title="Download PDF"
          @click="downloadMessagePdf"
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
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </svg>
          PDF
        </AppButton>
        <input
          ref="uploadInput"
          type="file"
          multiple
          style="display: none"
          @change="onUploadFilesChange"
        />
      </div>
      <div v-if="msg.role === 'assistant' && !msg.content && !msg.id && !isWelcome">
        <div v-if="msg.generatingImage" class="image-generating-label">
          <span v-if="msg.imageAnnouncement">🎨 {{ msg.imageAnnouncement }}</span>
          <span v-else>🎨 Generating image, please wait...</span>
        </div>
        <div class="typing-dots">
          <span></span><span></span><span></span>
        </div>
      </div>

      <!-- Welcome message with file preview: 2-column on desktop, stacked on mobile -->
      <div v-else-if="welcomeHasFiles && msg.role === 'assistant'" class="welcome-two-col">
        <div class="welcome-left-col">
          <div
            ref="messageContentEl"
            class="message-content-wrap"
            :class="{ 'animate-in': animateIn, 'is-translating': isTranslating }"
          >
            <div v-for="(part, pi) in contentParts" :key="pi">
              <!-- eslint-disable-next-line vue/no-v-html -->
              <div
                v-if="part.type === 'text'"
                ref="contentEls"
                class="markdown-content"
                @click="onContentClick"
                v-html="part.html"
              ></div>
              <QuizBlock
                v-else-if="part.type === 'quiz'"
                :quiz="part.quiz"
                :message-id="msg.id"
                :quiz-index="part.quizIndex"
                :conversation-name="conversationName"
                :file-name="fileName"
              />
              <MermaidBlock v-else-if="part.type === 'mermaid'" :code="part.code" />
            </div>
          </div>

          <!-- Mobile-only: small file thumbnails (old layout) -->
          <div class="welcome-file-previews-mobile">
            <div
              v-for="file in files"
              :key="file.id"
              class="file-preview-card"
              @click="openFilePreview(file)"
            >
              <div v-if="isImageFile(file)" class="file-preview-thumb">
                <img :src="getFileUrl(file)" :alt="file.originalName" loading="lazy" />
              </div>
              <div v-else-if="isPdfFile(file)" class="file-preview-thumb pdf-thumb">
                <object
                  v-if="getPdfEmbedUrl(file)"
                  :data="getPdfEmbedUrl(file)"
                  type="application/pdf"
                  class="pdf-mini-object"
                >
                  <div class="pdf-fallback-icon">
                    <svg
                      width="28"
                      height="28"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="1.5"
                    >
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <polyline points="14 2 14 8 20 8" />
                      <line x1="16" y1="13" x2="8" y2="13" />
                      <line x1="16" y1="17" x2="8" y2="17" />
                      <polyline points="10 9 9 9 8 9" />
                    </svg>
                  </div>
                </object>
                <div v-else class="pdf-fallback-icon">
                  <svg
                    width="28"
                    height="28"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.5"
                  >
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                    <line x1="16" y1="13" x2="8" y2="13" />
                    <line x1="16" y1="17" x2="8" y2="17" />
                    <polyline points="10 9 9 9 8 9" />
                  </svg>
                </div>
                <div class="pdf-click-overlay"></div>
              </div>
              <div v-else class="file-preview-thumb text-thumb">
                <svg
                  width="28"
                  height="28"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.5"
                >
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <polyline points="10 9 9 9 8 9" />
                </svg>
              </div>
              <span class="file-preview-name">{{ file.originalName }}</span>
            </div>
          </div>

          <div v-if="isWelcome && welcomeVisibleQuestions.length" class="welcome-suggested-questions" :class="{ 'is-translating': isTranslating }">
            <div
              v-for="question in welcomeVisibleQuestions"
              :key="question.raw"
              class="question-pill"
              role="button"
              tabindex="0"
              @click="onSuggestedQuestionClick($event, question.raw)"
              @keydown="onSuggestedQuestionKeydown($event, question.raw)"
            >
              <!-- eslint-disable-next-line vue/no-v-html -->
              <span class="suggested-question-markdown" v-html="question.html"></span>
            </div>
            <VDropdown
              v-if="welcomeHiddenQuestions.length"
              ref="welcomeMoreDropdown"
              theme="more-questions"
              :distance="6"
            >
              <div class="question-pill" role="button" tabindex="0">More ...</div>
              <template #popper>
                <div class="welcome-more-popper" role="menu">
                  <div
                    v-for="question in welcomeHiddenQuestions"
                    :key="`more-${question.raw}`"
                    class="question-pill welcome-more-item"
                    role="menuitem"
                    tabindex="0"
                    @click="onSuggestedQuestionClick($event, question.raw)"
                    @keydown="onSuggestedQuestionKeydown($event, question.raw)"
                  >
                    <!-- eslint-disable-next-line vue/no-v-html -->
                    <span class="suggested-question-markdown" v-html="question.html"></span>
                  </div>
                </div>
              </template>
            </VDropdown>
          </div>

          <div
            v-if="isFirstMessage && canUpload && (selectedUploadFiles.length || uploadError)"
            class="welcome-upload-row"
          >
            <template v-if="selectedUploadFiles.length">
              <span v-for="file in selectedUploadFiles" :key="file.name" class="upload-file-name">{{
                file.name
              }}</span>
              <span v-if="uploadingFiles" class="upload-file-status"><UploadingDots /></span>
            </template>
            <span v-if="uploadError" class="upload-error">{{ uploadError }}</span>
          </div>
        </div>

        <!-- Desktop-only: large preview in right column (carousel if 2+ files) -->
        <div class="welcome-right-col" @click="openFilePreview(currentPreviewFile!)">
          <!-- Left arrow (only if multiple files) -->
          <button
            v-if="hasMultipleFiles"
            class="carousel-arrow carousel-arrow-left"
            title="Previous file"
            @click="prevPreviewFile($event)"
          >
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>

          <div v-if="isImageFile(currentPreviewFile!)" class="welcome-preview-large">
            <img
              :src="getFileUrl(currentPreviewFile!)"
              :alt="currentPreviewFile!.originalName"
              loading="lazy"
            />
          </div>
          <div
            v-else-if="isPdfFile(currentPreviewFile!)"
            class="welcome-preview-large pdf-preview-large"
          >
            <object
              v-if="getPdfEmbedUrl(currentPreviewFile!)"
              :data="getPdfEmbedUrl(currentPreviewFile!)"
              type="application/pdf"
              class="pdf-large-object"
            >
              <div class="pdf-fallback-icon-large">
                <svg
                  width="48"
                  height="48"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.5"
                >
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <polyline points="10 9 9 9 8 9" />
                </svg>
                <span class="pdf-fallback-label">{{ currentPreviewFile!.originalName }}</span>
              </div>
            </object>
            <div v-else class="pdf-fallback-icon-large">
              <svg
                width="48"
                height="48"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
              >
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
                <polyline points="10 9 9 9 8 9" />
              </svg>
              <span class="pdf-fallback-label">{{ currentPreviewFile!.originalName }}</span>
            </div>
            <div class="pdf-click-overlay"></div>
          </div>
          <div v-else class="welcome-preview-large text-preview-large">
            <svg
              width="48"
              height="48"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
            >
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10 9 9 9 8 9" />
            </svg>
            <span class="text-fallback-label">{{ currentPreviewFile!.originalName }}</span>
          </div>

          <!-- Right arrow (only if multiple files) -->
          <button
            v-if="hasMultipleFiles"
            class="carousel-arrow carousel-arrow-right"
            title="Next file"
            @click="nextPreviewFile($event)"
          >
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>

          <span class="welcome-preview-name">{{ currentPreviewFile!.originalName }}</span>
          <!-- File counter dots -->
          <div v-if="hasMultipleFiles" class="carousel-dots">
            <span
              v-for="(_, i) in files"
              :key="i"
              class="carousel-dot"
              :class="{ active: i === previewFileIndex }"
            ></span>
          </div>
        </div>
      </div>

      <!-- Regular assistant content -->
      <template v-else-if="msg.role === 'assistant'">
        <div
          ref="messageContentEl"
          class="message-content-wrap"
          :class="{ 'animate-in': animateIn, 'is-translating': isTranslating }"
        >
          <div v-for="(part, pi) in contentParts" :key="pi">
            <!-- eslint-disable-next-line vue/no-v-html -->
            <div
              v-if="part.type === 'text'"
              ref="contentEls"
              class="markdown-content"
              @click="onContentClick"
              v-html="part.html"
            ></div>
            <QuizBlock
              v-else-if="part.type === 'quiz'"
              :quiz="part.quiz"
              :message-id="msg.id"
              :quiz-index="part.quizIndex"
              :conversation-name="conversationName"
              :file-name="fileName"
            />
            <MermaidBlock v-else-if="part.type === 'mermaid'" :code="part.code" />
          </div>
        </div>
        <div
          v-if="!msg.id && !isWelcome && (msg.generatingImage || imagesPending)"
          class="typing-dots"
        >
          <span></span><span></span><span></span>
        </div>
      </template>
      <span v-else class="user-text" :class="{ 'animate-in': animateIn, 'is-translating': isTranslating }">{{ msg.content }}</span>

      <!-- Inline suggested questions for welcome message (non-2-col fallback) -->
      <div v-if="isWelcome && !welcomeHasFiles && welcomeVisibleQuestions.length" class="welcome-suggested-questions" :class="{ 'is-translating': isTranslating }">
        <div
          v-for="question in welcomeVisibleQuestions"
          :key="question.raw"
          class="question-pill"
          role="button"
          tabindex="0"
          @click="onSuggestedQuestionClick($event, question.raw)"
          @keydown="onSuggestedQuestionKeydown($event, question.raw)"
        >
          <!-- eslint-disable-next-line vue/no-v-html -->
          <span class="suggested-question-markdown" v-html="question.html"></span>
        </div>
        <VDropdown
          v-if="welcomeHiddenQuestions.length"
          ref="welcomeMoreDropdown"
          theme="more-questions"
          :distance="6"
        >
          <div class="question-pill" role="button" tabindex="0">More ...</div>
          <template #popper>
            <div class="welcome-more-popper" role="menu">
              <div
                v-for="question in welcomeHiddenQuestions"
                :key="`more-${question.raw}`"
                class="question-pill welcome-more-item"
                role="menuitem"
                tabindex="0"
                @click="onSuggestedQuestionClick($event, question.raw)"
                @keydown="onSuggestedQuestionKeydown($event, question.raw)"
              >
                <!-- eslint-disable-next-line vue/no-v-html -->
                <span class="suggested-question-markdown" v-html="question.html"></span>
              </div>
            </div>
          </template>
        </VDropdown>
      </div>

      <!-- Upload files button (first message only, non-2-col fallback) -->
      <div
        v-if="
          isFirstMessage &&
          canUpload &&
          !welcomeHasFiles &&
          (selectedUploadFiles.length || uploadError)
        "
        class="welcome-upload-row"
      >
        <template v-if="selectedUploadFiles.length">
          <span v-for="file in selectedUploadFiles" :key="file.name" class="upload-file-name">{{
            file.name
          }}</span>
          <span v-if="uploadingFiles" class="upload-file-status"><UploadingDots /></span>
        </template>
        <span v-if="uploadError" class="upload-error">{{ uploadError }}</span>
      </div>

      <!-- Inline image thumbnails from citations -->
      <div v-if="imageCitations.length" class="citation-images">
        <div
          v-for="(img, idx) in imageCitations"
          :key="idx"
          class="citation-image-thumb"
          @click="openImage(img)"
        >
          <img :src="img.url" :alt="img.section || 'Image'" loading="lazy" />
          <span class="citation-image-label">{{ img.section || 'Image' }}</span>
        </div>
      </div>

      <!-- Thread reply indicator (Slack-style) -->
      <div
        v-if="msg.threadReplyCount"
        class="thread-indicator"
        @click="$emit('view-threads', msg.id!)"
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
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
        <span class="thread-count"
          >{{ msg.threadReplyCount }} {{ msg.threadReplyCount === 1 ? 'reply' : 'replies' }}</span
        >
      </div>

      <ImageModal :visible="modalOpen" :src="modalSrc" :alt="modalAlt" @close="modalOpen = false" />

      <SourcePreviewModal
        v-if="previewCitation"
        :visible="previewOpen"
        :citation="previewCitation"
        :conversation-id="effectiveStorageId"
        @close="previewOpen = false"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount, onMounted } from 'vue'
import { createTooltip, destroyTooltip, Dropdown as VDropdownType } from 'floating-vue'
import { computePosition, flip, shift, offset } from '@floating-ui/dom'
import type { ChatMessage, ConversationStatus } from '../api'
import { getStorageUrl, resolveStorageUrl } from '../api'
import { getUserId } from '../utils/fingerprint'
import { renderMarkdown, renderInlineMarkdown } from '../utils/markdown'
import ImageModal from './ImageModal.vue'
import SourcePreviewModal from './SourcePreviewModal.vue'
import AppButton from './AppButton.vue'
import { defineAsyncComponent } from 'vue'
const QuizBlock = defineAsyncComponent(() => import('./QuizBlock.vue'))
const MermaidBlock = defineAsyncComponent(() => import('./MermaidBlock.vue'))
import type { QuizData } from './QuizBlock.vue'
import { getData, setData } from '../utils/localData'
import UploadingDots from './UploadingDots.vue'

const MAX_VISIBLE_WELCOME_PROMPTS = 5
const MAX_VISIBLE_ASSISTANT_ACTIONS = 3
const outsideClickHandlers = new Set<(event: MouseEvent) => void>()
let outsideClickListenerBound = false

function dispatchOutsideClick(event: MouseEvent) {
  outsideClickHandlers.forEach((handler) => handler(event))
}

function registerOutsideClickHandler(handler: (event: MouseEvent) => void) {
  outsideClickHandlers.add(handler)
  if (!outsideClickListenerBound) {
    document.addEventListener('click', dispatchOutsideClick)
    outsideClickListenerBound = true
  }
}

function unregisterOutsideClickHandler(handler: (event: MouseEvent) => void) {
  outsideClickHandlers.delete(handler)
  if (!outsideClickHandlers.size && outsideClickListenerBound) {
    document.removeEventListener('click', dispatchOutsideClick)
    outsideClickListenerBound = false
  }
}

const props = defineProps<{
  msg: ChatMessage
  asking: boolean
  conversationId: string
  storageConversationId?: string
  isWelcome?: boolean
  isFirstMessage?: boolean
  canUpload?: boolean
  files?: ConversationStatus['files']
  suggestedQuestions?: string[]
  conversationName?: string
  fileName?: string
  isThread?: boolean
  noAnimation?: boolean
  isTranslating?: boolean
}>()

const animateIn = ref(!props.noAnimation)
onMounted(() => {
  registerOutsideClickHandler(onDocumentClick)
  if (animateIn.value)
    setTimeout(() => {
      animateIn.value = false
    }, 400)
})

// Use storageConversationId for file URLs (for threads, points to parent's storage)
const effectiveStorageId = computed(() => props.storageConversationId || props.conversationId)

const emit = defineEmits<{
  'select-question': [question: string]
  'upload-files': [files: File[]]
  'trigger-upload': []
  'view-threads': [messageId: string]
  // Fired whenever a dynamically added `<img>` has finished its load cycle.
  // `success` is false when the image exhausted its retry budget and was
  // revealed as a broken-image placeholder, so parents can decide whether
  // to scroll or ignore.
  'image-revealed': [success: boolean]
}>()

const senderLabel = computed(() => {
  if (props.msg.role === 'assistant') return 'Assistant'
  // In thread conversations, show "userN" for other users
  if (props.isThread && props.msg.userId) {
    const myId = getUserId()
    if (myId !== null && props.msg.userId === myId) return 'You'
    return `user${props.msg.userId}`
  }
  return 'You'
})

// Upload files state (for first message inline upload)
const uploadInput = ref<HTMLInputElement | null>(null)
const selectedUploadFiles = ref<File[]>([])
const uploadingFiles = ref(false)
const uploadError = ref('')

const welcomeHasFiles = computed(() => props.isWelcome && (props.files?.length ?? 0) > 0)

// File carousel for right-column preview (when 2+ files uploaded)
const previewFileIndex = ref(0)
const hasMultipleFiles = computed(() => (props.files?.length ?? 0) > 1)
const currentPreviewFile = computed(() => props.files?.[previewFileIndex.value] ?? props.files?.[0])

function nextPreviewFile(event: Event) {
  event.stopPropagation()
  if (!props.files?.length) return
  previewFileIndex.value = (previewFileIndex.value + 1) % props.files.length
}

function prevPreviewFile(event: Event) {
  event.stopPropagation()
  if (!props.files?.length) return
  previewFileIndex.value = (previewFileIndex.value - 1 + props.files.length) % props.files.length
}

function onUploadFilesChange(event: Event) {
  const target = event.target as HTMLInputElement
  const allFiles = Array.from(target.files || [])
  const videoFiles = allFiles.filter((f) => f.type.startsWith('video/'))
  const validFiles = allFiles.filter((f) => !f.type.startsWith('video/'))
  if (videoFiles.length) {
    uploadError.value = 'Video files are not supported.'
  } else {
    uploadError.value = ''
  }
  selectedUploadFiles.value = validFiles
  if (validFiles.length) {
    doUploadFiles()
  }
}

function doUploadFiles() {
  if (!selectedUploadFiles.value.length) return
  emit('upload-files', selectedUploadFiles.value)
}

function resetUploadState(error?: string) {
  selectedUploadFiles.value = []
  uploadingFiles.value = false
  uploadError.value = error || ''
  if (uploadInput.value) uploadInput.value.value = ''
}

// Share message
const shareCopied = ref(false)
function shareMessage() {
  if (props.msg.id) {
    const url = `${window.location.origin}/m/${props.msg.id}`
    navigator.clipboard.writeText(url)
  } else {
    const url = `${window.location.origin}/c/${props.conversationId}`
    navigator.clipboard.writeText(url)
  }
  shareCopied.value = true
  setTimeout(() => {
    shareCopied.value = false
  }, 2000)
}

function setUploading(val: boolean) {
  uploadingFiles.value = val
}

function triggerUpload() {
  uploadInput.value?.click()
}

defineExpose({ resetUploadState, setUploading, triggerUpload })

const _renderedContent = computed(() => renderMarkdown(props.msg.content))
const renderedSuggestedQuestions = computed(() =>
  (props.suggestedQuestions ?? []).map((question) => ({
    raw: question,
    html: renderInlineMarkdown(question),
  })),
)
const welcomeMoreDropdown = ref<InstanceType<typeof VDropdownType> | null>(null)
const welcomeVisibleQuestions = computed(() =>
  renderedSuggestedQuestions.value.slice(0, MAX_VISIBLE_WELCOME_PROMPTS),
)
const welcomeHiddenQuestions = computed(() =>
  renderedSuggestedQuestions.value.slice(MAX_VISIBLE_WELCOME_PROMPTS),
)

function onSuggestedQuestionClick(event: MouseEvent, question: string) {
  const target = event.target as HTMLElement | null
  if (target?.closest('a')) return
  closeWelcomeMore()
  closeActionMenus()
  emit('select-question', question)
}

function onSuggestedQuestionKeydown(event: KeyboardEvent, question: string) {
  const target = event.target as HTMLElement | null
  if (target?.closest('a')) return
  if (event.key === 'Escape') {
    closeWelcomeMore()
    closeActionMenus()
    return
  }
  if (event.key !== 'Enter' && event.key !== ' ') return
  if (event.key === ' ') event.preventDefault()
  closeWelcomeMore()
  closeActionMenus()
  emit('select-question', question)
}

function closeWelcomeMore() {
  welcomeMoreDropdown.value?.hide()
}

const messageContentEl = ref<HTMLElement | null>(null)
const messageRootEl = ref<HTMLElement | null>(null)

/** Show PDF download button for all assistant messages with content,
 *  except those with quiz blocks (they have their own PDF button). */
const hasRichContent = computed(() => {
  if (props.msg.role !== 'assistant' || !props.msg.content) return false
  const parts = contentParts.value
  if (parts.some((p) => p.type === 'quiz')) return false
  return true
})

async function downloadMessagePdf() {
  const title = props.conversationName || 'chatrag'

  // Patch markdown with current checklist checked states from the DOM
  let md = props.msg.content
  const boxes: boolean[] = []
  for (const el of contentEls.value ?? []) {
    el.querySelectorAll('.checklist-box').forEach((box) => {
      boxes.push(box.classList.contains('checked'))
    })
  }
  if (boxes.length) {
    let idx = 0
    md = md.replace(/^(\s*[-*+]\s+\[)([ xX])(\]\s+)/gm, (match, before, check, after) => {
      if (idx < boxes.length) {
        const checked = boxes[idx++]
        return `${before}${checked ? 'x' : ' '}${after}`
      }
      return match
    })
  }

  try {
    const { printContentAsPdf } = await import('../utils/printPdf')
    await printContentAsPdf(md, title)
  } catch (err) {
    console.error('PDF generation failed:', err)
    alert('PDF generation failed. Please reload the page and try again.')
  }
}

type ContentPart =
  | { type: 'text'; html: string }
  | { type: 'quiz'; quiz: QuizData; quizIndex: number }
  | { type: 'mermaid'; code: string }

// Mermaid diagram detection regex: ```mermaid ... ```
const mermaidBlockRe = /```mermaid\s*\n([\s\S]*?)```/g

/** Split a text chunk into interleaved text and mermaid parts */
function splitMermaid(text: string): ContentPart[] {
  const result: ContentPart[] = []
  let lastIdx = 0
  for (const m of text.matchAll(mermaidBlockRe)) {
    const before = text.slice(lastIdx, m.index)
    if (before.trim()) result.push({ type: 'text', html: renderMarkdown(before) })
    result.push({ type: 'mermaid', code: m[1].trim() })
    lastIdx = m.index! + m[0].length
  }
  const after = text.slice(lastIdx)
  if (after.trim()) result.push({ type: 'text', html: renderMarkdown(after) })
  return result
}

const contentParts = computed<ContentPart[]>(() => {
  const content = props.msg.content
  const parts: ContentPart[] = []
  const marker = '[quiz:'
  let lastIndex = 0
  let searchFrom = 0
  let quizCounter = 0

  while (searchFrom < content.length) {
    const start = content.indexOf(marker, searchFrom)
    if (start === -1) break

    const jsonStart = start + marker.length
    // Find matching closing brace by counting braces
    let depth = 0
    let jsonEnd = -1
    for (let i = jsonStart; i < content.length; i++) {
      if (content[i] === '{') depth++
      else if (content[i] === '}') {
        depth--
        if (depth === 0) {
          // Expect ] after the closing brace (allow optional whitespace)
          let j = i + 1
          while (j < content.length && /\s/.test(content[j])) j++
          if (j < content.length && content[j] === ']') {
            jsonEnd = j // points to ']'
          }
          break
        }
      }
    }

    if (jsonEnd === -1) {
      searchFrom = start + marker.length
      continue
    }

    // Text before quiz (may contain mermaid blocks)
    const textBefore = content.slice(lastIndex, start)
    if (textBefore.trim()) {
      parts.push(...splitMermaid(textBefore))
    }

    // Parse quiz JSON — strip [source:N] citations that break JSON validity
    const jsonStr = content.slice(jsonStart, jsonEnd).replace(/\[source:\s*\d+\]/g, '')
    try {
      const quizData = JSON.parse(jsonStr) as QuizData
      if (quizData.title && Array.isArray(quizData.questions)) {
        // Normalize correct field to always be an array
        for (const q of quizData.questions) {
          if (!Array.isArray(q.correct)) {
            q.correct = [q.correct as unknown as number]
          }
        }
        // Default multiple to true if not specified (backward compat)
        if (typeof quizData.multiple !== 'boolean') {
          quizData.multiple = quizData.questions.some((q) => q.correct.length > 1)
        }
        parts.push({ type: 'quiz', quiz: quizData, quizIndex: quizCounter++ })
      } else {
        parts.push(...splitMermaid(content.slice(start, jsonEnd + 1)))
      }
    } catch {
      parts.push(...splitMermaid(content.slice(start, jsonEnd + 1)))
    }

    lastIndex = jsonEnd + 1
    searchFrom = lastIndex
  }

  // Remaining text after last quiz block (or all text if no quiz)
  const remaining = content.slice(lastIndex)
  if (remaining.trim()) {
    parts.push(...splitMermaid(remaining))
  }

  // If no parts at all, add empty text
  if (!parts.length) {
    parts.push({ type: 'text', html: renderMarkdown(content) })
  }

  return parts
})

// Source preview modal state
const previewOpen = ref(false)
const previewCitation = ref<{
  fileName: string
  chunkId: string
  text: string
  section?: string
  page?: number | null
  imageName?: string
}>()

// Tooltip management for inline source buttons
const contentEls = ref<HTMLElement[]>([])
const tooltipElements: HTMLElement[] = []
const MAX_TOOLTIP_LENGTH = 600

// Tracks whether any <img> inside the rendered markdown is still loading.
// Freshly generated images (AI/Pollinations) occasionally take a few seconds
// to become reachable after the assistant response returns, which produces a
// flash of a broken image. We hide such images until they actually decode,
// show the typing-dots indicator instead, and auto-retry failed loads with
// exponential backoff.
const imagesPending = ref(false)
const trackedImages = new Set<HTMLImageElement>()
const pendingImages = new Set<HTMLImageElement>()
const imageRetryTimers = new Set<ReturnType<typeof setTimeout>>()
// URLs of images we've successfully revealed once. When v-html re-renders the
// markdown (e.g. after a translation swap) the <img> is a brand new DOM node
// even though the resource is identical. We use this set to skip the
// hide-until-loaded + fade-in treatment for repeated sources so translations
// don't visibly re-animate the picture.
const seenImageSources = new Set<string>()

function imageSrcKey(img: HTMLImageElement): string {
  const raw = img.getAttribute('src') || ''
  return raw.split('?')[0].split('#')[0]
}
const IMG_MAX_ATTEMPTS = 8
let componentUnmounted = false
// First tracking pass corresponds to images already present when the component
// mounts (conversation history). Images added in subsequent passes are the
// ones that arrive dynamically (e.g. post-generation polling) and should
// animate into view.
let initialImageTrackingDone = false

function updateImagesPending() {
  imagesPending.value = pendingImages.size > 0
}

// Pre-sizes the `.markdown-image-scroll` wrapper to the image's rendered box
// (natural aspect ratio, capped by the same max-height the CSS applies).
// Reserving space before the <img> becomes visible lets the fade-in play into
// a stable container instead of causing a layout jump when the picture
// finally decodes.
function sizeImageContainer(img: HTMLImageElement) {
  const parent = img.parentElement
  if (!parent || !parent.classList.contains('markdown-image-scroll')) return
  const nw = img.naturalWidth
  const nh = img.naturalHeight
  if (!nw || !nh) return
  const maxH = Math.min(window.innerHeight * 0.7, 420)
  const height = Math.min(nh, maxH)
  const width = nw * (height / nh)
  parent.style.width = `${width}px`
  parent.style.height = `${height}px`
}

function revealImage(img: HTMLImageElement, success = true) {
  // The underlying <img> load/error events may fire after onBeforeUnmount
  // (listeners aren't forcibly removed), so guard against emitting events
  // or touching reactive state from an unmounted instance.
  if (componentUnmounted) return
  if (success && img.naturalWidth > 0 && img.naturalHeight > 0) {
    sizeImageContainer(img)
  }
  img.style.removeProperty('display')
  const wasDynamic = img.dataset.animateIn === 'true'
  if (wasDynamic && success) {
    img.classList.add('animate-in')
  }
  const key = imageSrcKey(img)
  if (key) seenImageSources.add(key)
  pendingImages.delete(img)
  updateImagesPending()
  // Notify parent so it can re-scroll to focus on the newly visible image,
  // matching the smooth scroll effect used for streamed assistant text.
  if (wasDynamic) {
    emit('image-revealed', success)
  }
}

function attachImgListeners(img: HTMLImageElement, attempt: number) {
  const onLoad = () => {
    cleanup()
    revealImage(img)
  }
  const onError = () => {
    cleanup()
    scheduleImgRetry(img, attempt)
  }
  const cleanup = () => {
    img.removeEventListener('load', onLoad)
    img.removeEventListener('error', onError)
  }
  img.addEventListener('load', onLoad)
  img.addEventListener('error', onError)

  // If the image already resolved before we attached listeners (browser cache
  // or immediate failure), handle its state synchronously.
  if (img.complete) {
    cleanup()
    if (img.naturalWidth > 0) revealImage(img)
    else scheduleImgRetry(img, attempt)
  }
}

function scheduleImgRetry(img: HTMLImageElement, attempt: number) {
  if (componentUnmounted) return
  if (attempt >= IMG_MAX_ATTEMPTS) {
    // Give up: reveal the (broken) image so the user at least sees a cue.
    revealImage(img, false)
    return
  }
  const baseSrc = img.dataset.origSrc || img.src.split('?')[0].split('#')[0]
  img.dataset.origSrc = baseSrc
  const delay = Math.min(500 * 2 ** attempt, 8000)
  const timer = setTimeout(() => {
    imageRetryTimers.delete(timer)
    if (componentUnmounted) return
    img.src = `${baseSrc}?retry=${attempt + 1}&ts=${Date.now()}`
    attachImgListeners(img, attempt + 1)
  }, delay)
  imageRetryTimers.add(timer)
}

function trackContentImages() {
  if (!contentEls.value?.length) return
  for (const el of contentEls.value) {
    const imgs = el.querySelectorAll<HTMLImageElement>('img')
    imgs.forEach((img) => {
      if (trackedImages.has(img)) return
      trackedImages.add(img)
      const key = imageSrcKey(img)
      // Same resource we've already shown (e.g. v-html re-render after a
      // translation swap): display it immediately without the fade-in
      // treatment so the picture appears stable across translations.
      if (key && seenImageSources.has(key)) {
        return
      }
      // Only flag images that appear after the initial mount pass so we don't
      // animate conversation history on page load.
      if (initialImageTrackingDone) {
        img.dataset.animateIn = 'true'
      }
      // Hide until decode succeeds so users never see a broken-image icon.
      img.style.display = 'none'
      pendingImages.add(img)
      attachImgListeners(img, 0)
    })
  }
  initialImageTrackingDone = true
  updateImagesPending()
}

function clearImageTracking() {
  imageRetryTimers.forEach((t) => clearTimeout(t))
  imageRetryTimers.clear()
  trackedImages.clear()
  pendingImages.clear()
  seenImageSources.clear()
  imagesPending.value = false
}

function truncateText(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text
  return text.slice(0, maxLen) + '…'
}

function setupTooltips() {
  cleanupTooltips()
  if (!contentEls.value?.length) return
  for (const el of contentEls.value) {
    const buttons = el.querySelectorAll<HTMLElement>('.inline-source-btn')
    buttons.forEach((btn) => {
      const idx = parseInt(btn.dataset.sourceIdx || '0', 10) - 1
      const citation = props.msg.citations?.[idx]
      if (!citation?.text) return
      createTooltip(
        btn,
        {
          content: truncateText(citation.text, MAX_TOOLTIP_LENGTH),
          delay: { show: 500, hide: 0 },
          themes: ['tooltip'],
        },
        false,
      )
      tooltipElements.push(btn)
    })
  }
}

function cleanupTooltips() {
  tooltipElements.forEach((el) => {
    try {
      destroyTooltip(el)
    } catch { /* tooltip already destroyed */ }
  })
  tooltipElements.length = 0
}

function injectCodeCopyButtons() {
  if (!contentEls.value?.length) return
  for (const el of contentEls.value) {
    const pres = el.querySelectorAll<HTMLPreElement>('pre')
    pres.forEach((pre) => {
      if (pre.querySelector('.code-copy-btn')) return
      // Wrap pre in a relative container
      const wrapper = document.createElement('div')
      wrapper.className = 'code-block-wrapper'
      pre.parentNode!.insertBefore(wrapper, pre)
      wrapper.appendChild(pre)

      const btn = document.createElement('button')
      btn.className = 'code-copy-btn'
      btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copy text`
      btn.addEventListener('click', () => {
        const code = pre.querySelector('code')
        navigator.clipboard.writeText(code?.textContent || pre.textContent || '')
        btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Copied!`
        setTimeout(() => {
          btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copy text`
        }, 2000)
      })
      wrapper.appendChild(btn)
    })
  }
}

function transformActionButtonGroups() {
  if (!contentEls.value?.length) return
  for (const el of contentEls.value) {
    const rows = el.querySelectorAll<HTMLElement>('.action-btns-row')
    rows.forEach((row) => {
      if (row.dataset.moreReady === '1') return
      const buttons = Array.from(row.querySelectorAll<HTMLElement>(':scope > .action-btn'))
      if (buttons.length <= MAX_VISIBLE_ASSISTANT_ACTIONS) {
        // Only lock this row when streaming is done — during streaming more buttons may still arrive
        if (!props.asking) row.dataset.moreReady = '1'
        return
      }
      const visibleButtons = buttons.slice(0, MAX_VISIBLE_ASSISTANT_ACTIONS)
      const rest = buttons.slice(MAX_VISIBLE_ASSISTANT_ACTIONS)
      const wrap = document.createElement('span')
      wrap.className = 'action-more-wrap'
      const visibleRow = document.createElement('span')
      visibleRow.className = 'action-visible-row'
      const overflowWrap = document.createElement('span')
      overflowWrap.className = 'action-overflow-wrap'

      const moreBtn = document.createElement('button')
      moreBtn.className = 'action-btn action-more-btn'
      moreBtn.type = 'button'
      moreBtn.textContent = 'More ...'
      moreBtn.setAttribute('aria-haspopup', 'menu')
      moreBtn.setAttribute('aria-expanded', 'false')

      const menu = document.createElement('span')
      menu.className = 'action-more-menu'
      rest.forEach((btn) => {
        btn.classList.add('action-more-item')
        menu.appendChild(btn)
      })

      visibleButtons.forEach((btn) => {
        visibleRow.appendChild(btn)
      })
      overflowWrap.appendChild(moreBtn)
      overflowWrap.appendChild(menu)
      wrap.appendChild(visibleRow)
      wrap.appendChild(overflowWrap)
      row.replaceChildren(wrap)
      row.dataset.moreReady = '1'
    })
  }
}

function closeActionMenus() {
  if (!messageContentEl.value) return
  const openMenus = messageContentEl.value.querySelectorAll<HTMLElement>('.action-more-wrap.open')
  openMenus.forEach((wrap) => {
    wrap.classList.remove('open')
    const btn = wrap.querySelector<HTMLElement>('.action-more-btn')
    if (btn) btn.setAttribute('aria-expanded', 'false')
    const menu = wrap.querySelector<HTMLElement>('.action-more-menu')
    if (menu) {
      menu.style.left = ''
      menu.style.top = ''
      menu.style.visibility = ''
    }
  })
}

let postProcessTimer: ReturnType<typeof setTimeout> | null = null

watch(
  contentParts,
  () => {
    if (postProcessTimer) clearTimeout(postProcessTimer)
    postProcessTimer = setTimeout(() => {
      setupTooltips()
      restoreChecklistState()
      injectCodeCopyButtons()
      transformActionButtonGroups()
      trackContentImages()
    }, 150)
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  componentUnmounted = true
  unregisterOutsideClickHandler(onDocumentClick)
  cleanupTooltips()
  clearImageTracking()
  if (postProcessTimer) clearTimeout(postProcessTimer)
})

function saveChecklistState() {
  if (!props.msg.id) return
  const states: boolean[] = []
  for (const el of contentEls.value ?? []) {
    el.querySelectorAll('.checklist-box').forEach((box) => {
      states.push(box.classList.contains('checked'))
    })
  }
  if (states.length) {
    setData(`checklist:${props.msg.id}`, states)
  }
}

function restoreChecklistState() {
  if (!props.msg.id) return
  try {
    const states = getData<boolean[]>(`checklist:${props.msg.id}`)
    if (!states) return
    let idx = 0
    for (const el of contentEls.value ?? []) {
      el.querySelectorAll('.checklist-box').forEach((box) => {
        if (idx < states.length && states[idx]) box.classList.add('checked')
        idx++
      })
    }
  } catch {
    /* ignore corrupt data */
  }
}

function onContentClick(e: MouseEvent) {
  // Handle inline image clicks — open in modal
  const img = (e.target as HTMLElement).closest('img') as HTMLImageElement | null
  if (img && img.src) {
    modalSrc.value = img.src
    modalAlt.value = img.alt || 'Image'
    modalOpen.value = true
    return
  }

  // Handle source citation clicks (higher priority than checklist)
  const btn = (e.target as HTMLElement).closest('.inline-source-btn') as HTMLElement | null
  if (btn) {
    const idx = parseInt(btn.dataset.sourceIdx || '0', 10) - 1 // 1-based to 0-based
    if (props.msg.citations && props.msg.citations[idx]) {
      previewCitation.value = props.msg.citations[idx]
      previewOpen.value = true
    }
    return
  }

  // Handle action button clicks
  const actionMoreBtn = (e.target as HTMLElement).closest('.action-more-btn') as HTMLElement | null
  if (actionMoreBtn) {
    const wrap = actionMoreBtn.closest('.action-more-wrap') as HTMLElement | null
    if (!wrap) return
    const isOpen = wrap.classList.contains('open')
    closeActionMenus()
    if (!isOpen) {
      const menu = wrap.querySelector<HTMLElement>('.action-more-menu')
      if (menu) {
        // Hide temporarily to avoid flash of incorrectly-positioned content
        // while computePosition runs its async DOM measurements
        menu.style.visibility = 'hidden'
        wrap.classList.add('open')
        actionMoreBtn.setAttribute('aria-expanded', 'true')
        computePosition(actionMoreBtn, menu, {
          placement: 'right-start',
          strategy: 'fixed',
          middleware: [
            offset(8),
            flip({ fallbackPlacements: ['left-start', 'bottom-start', 'top-start'] }),
            shift({ padding: 8 }),
          ],
        })
          .then(({ x, y }) => {
            menu.style.left = `${x}px`
            menu.style.top = `${y}px`
            menu.style.visibility = ''
          })
          .catch(() => {
            // Ensure the menu is always visible even if positioning fails
            menu.style.visibility = ''
          })
      } else {
        wrap.classList.add('open')
        actionMoreBtn.setAttribute('aria-expanded', 'true')
      }
    }
    return
  }
  const actionBtn = (e.target as HTMLElement).closest('.action-btn') as HTMLElement | null
  if (actionBtn) {
    if (actionBtn.dataset.upload) {
      closeActionMenus()
      emit('trigger-upload')
      return
    }
    const action = actionBtn.dataset.action
    if (action) {
      closeActionMenus()
      closeWelcomeMore()
      emit('select-question', action)
    }
    return
  }

  // Handle checklist checkbox clicks (clicking the box or anywhere on the row)
  const checkBox = (e.target as HTMLElement).closest('.checklist-box') as HTMLElement | null
  if (checkBox) {
    checkBox.classList.toggle('checked')
    saveChecklistState()
    return
  }
  const li = (e.target as HTMLElement).closest('li') as HTMLElement | null
  if (li && li.querySelector('.checklist-box')) {
    li.querySelector('.checklist-box')!.classList.toggle('checked')
    saveChecklistState()
    return
  }
}

function onDocumentClick(event: MouseEvent) {
  const target = event.target as HTMLElement | null
  if (!target) return
  const clickedMenu = target.closest('.action-more-wrap, .welcome-more-wrap')
  if (clickedMenu && messageRootEl.value?.contains(clickedMenu)) return
  // The welcome "More ..." uses floating-vue VDropdown with theme "more-questions".
  // Both the trigger wrapper (inside this message) and the teleported popper carry
  // the theme class, so we skip closing when either is clicked.
  if (target.closest('.v-popper--theme-more-questions')) return
  closeActionMenus()
  closeWelcomeMore()
}

// Image modal state
const modalOpen = ref(false)
const modalSrc = ref('')
const modalAlt = ref('')

type CitationEntry = NonNullable<ChatMessage['citations']>[number]

// @ts-ignore
type ImageCitationInfo = { url: string; section?: string; imageName: string }

function resolveImageCitation(citation: CitationEntry): ImageCitationInfo {
  return {
    // @ts-ignore
    url: getStorageUrl(effectiveStorageId.value, citation.imageName),
    section: citation.section,
    // @ts-ignore
    imageName: citation.imageName,
  }
}

const imageCitations = computed<ImageCitationInfo[]>(() => {
  if (!props.msg.citations) return []
  return props.msg.citations.filter((c) => c.imageName).map((c) => resolveImageCitation(c))
})

function openImage(img: ImageCitationInfo) {
  modalSrc.value = img.url
  modalAlt.value = img.section || 'Image'
  modalOpen.value = true
}

// Welcome message file preview helpers
type FileInfo = ConversationStatus['files'][number]

function isImageFile(file: FileInfo) {
  return file.mimeType.startsWith('image/')
}

function isPdfFile(file: FileInfo) {
  return file.mimeType === 'application/pdf'
}

function getFileUrl(file: FileInfo) {
  return getStorageUrl(effectiveStorageId.value, file.originalName)
}

// PDF embeds use a direct (already-resolved) URL so the browser doesn't follow
// a cross-origin redirect from /api/storage/... to a GCS signed URL with a
// `#page=...` fragment (which triggers Chrome's "Unsafe attempt to load URL"
// warning). Cache per storageId+filename to avoid re-requesting on re-renders.
const pdfEmbedUrlCache = ref(new Map<string, string>())
const pdfEmbedUrlInFlight = new Set<string>()

function pdfEmbedKey(file: FileInfo) {
  return `${effectiveStorageId.value}:${file.originalName}`
}

function getPdfEmbedUrl(file: FileInfo): string {
  const key = pdfEmbedKey(file)
  const cached = pdfEmbedUrlCache.value.get(key)
  if (cached) return `${cached}#page=1&view=FitH`
  if (!pdfEmbedUrlInFlight.has(key)) {
    pdfEmbedUrlInFlight.add(key)
    resolveStorageUrl(effectiveStorageId.value, file.originalName)
      .then((url) => {
        pdfEmbedUrlCache.value.set(key, url)
      })
      .catch(() => {
        // Fallback to same-origin proxy URL if resolution fails
        pdfEmbedUrlCache.value.set(key, getFileUrl(file))
      })
      .finally(() => {
        pdfEmbedUrlInFlight.delete(key)
      })
  }
  return ''
}

function openFilePreview(file: FileInfo) {
  if (isImageFile(file)) {
    modalSrc.value = getFileUrl(file)
    modalAlt.value = file.originalName
    modalOpen.value = true
  } else if (isPdfFile(file)) {
    previewCitation.value = {
      fileName: file.originalName,
      chunkId: '',
      text: '',
      page: 1,
    }
    previewOpen.value = true
  } else {
    // For text files, open in a new tab
    window.open(getFileUrl(file), '_blank')
  }
}
</script>

<style scoped>
.user-text {
  white-space: pre-wrap;
  margin: 6px 0 0;
  font-size: 15px;
  line-height: 1.6;
  display: block;
}

/* Message action buttons container */
.msg-actions {
  display: flex;
  gap: 6px;
  position: absolute;
  top: 10px;
  right: 14px;
  opacity: 0;
  transition: opacity 0.15s;
}

.msg-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: #242832;
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #64748b;
  border-radius: 8px;
  padding: 4px 10px;
  font-size: 11px;
  cursor: pointer;
  transition:
    background 0.15s,
    color 0.15s,
    border-color 0.15s;
  font-family: inherit;
}


/* On touch devices, always show and add spacing below */
@media (hover: none) {
  .msg-actions {
    opacity: 1;
    position: static;
    margin-bottom: 5px;
  }
}

@media (hover: hover) {
  .message:hover .msg-actions {
    opacity: 1;
  }
}

@media (hover: hover) {
  .msg-action-btn:hover {
    background: rgba(167, 139, 250, 0.12);
    border-color: rgba(167, 139, 250, 0.3);
    color: #c4b5fd;
  }
}
.msg-action-btn:active {
  background: rgba(167, 139, 250, 0.12);
  border-color: rgba(167, 139, 250, 0.3);
  color: #c4b5fd;
}

/* Inline source buttons */
:deep(.inline-source-btn) {
  display: inline-flex;
  align-items: center;
  gap: 1px;
  background: #7c3aed33;
  color: #c4b5fd;
  border: 1px solid #7c3aed55;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  padding: 0 5px;
  margin: 0 1px;
  cursor: pointer;
  vertical-align: super;
  line-height: 1.4;
  transition:
    background 0.15s,
    border-color 0.15s;
  font-family: inherit;
}

@media (hover: hover) {
  :deep(.inline-source-btn:hover) {
    background: #7c3aed2a;
    border-color: #a78bfa;
  }
}

:deep(.inline-source-icon) {
  font-size: 9px;
}

/* Image thumbnails */
.citation-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0 4px;
}

.citation-image-thumb {
  cursor: pointer;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #334155;
  transition:
    border-color 0.15s,
    transform 0.15s;
  max-width: 140px;
}

@media (hover: hover) {
  .citation-image-thumb:hover {
    border-color: #c4b5fd;
    transform: scale(1.03);
  }
}

.citation-image-thumb img {
  display: block;
  width: 140px;
  height: 100px;
  object-fit: cover;
}

.citation-image-label {
  display: block;
  padding: 4px 6px;
  font-size: 11px;
  color: #94a3b8;
  background: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.citation-active-image {
  margin: 8px 0;
  cursor: pointer;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #334155;
  display: inline-block;
  transition: border-color 0.15s;
}

@media (hover: hover) {
  .citation-active-image:hover {
    border-color: #c4b5fd;
  }
}

.citation-active-image img {
  display: block;
  max-width: 100%;
  max-height: 300px;
  object-fit: contain;
}

/* Welcome 2-column layout (desktop only) */
.welcome-two-col {
  display: flex;
  gap: 20px;
  min-height: 160px;
}

.welcome-left-col {
  flex: 1;
  min-width: 0;
}

/* Mobile: small file thumbnails (old layout) */
.welcome-file-previews-mobile {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 12px 0 4px;
}

.file-preview-card {
  cursor: pointer;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.04);
  transition:
    border-color 0.15s,
    transform 0.15s,
    background 0.15s;
  width: 120px;
  flex-shrink: 0;
}

@media (hover: hover) {
  .file-preview-card:hover {
    border-color: #a78bfa;
    background: rgba(167, 139, 250, 0.08);
    transform: scale(1.03);
  }
}

.file-preview-thumb {
  width: 120px;
  height: 90px;
  overflow: hidden;
  background: #0f172a;
  display: flex;
  align-items: center;
  justify-content: center;
}

.file-preview-thumb img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.file-preview-thumb.pdf-thumb {
  position: relative;
}

.pdf-mini-object {
  width: 120px;
  height: 90px;
  pointer-events: none;
  overflow: hidden;
}

.pdf-fallback-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: #64748b;
}

.file-preview-thumb.text-thumb {
  color: #64748b;
}

.file-preview-name {
  display: block;
  padding: 6px 8px;
  font-size: 11px;
  color: #94a3b8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Desktop: large right-column preview */
.welcome-right-col {
  position: relative;
  flex-shrink: 0;
  margin-right: -2px;
  margin-top: 15px;
  align-self: flex-start;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0;
  cursor: pointer;
  border-radius: 0;
  border: 1px solid transparent;
  /* background: rgba(255, 255, 255, 0.04); */
  transition:
    border-color 0.15s,
    background 0.15s;
  overflow: hidden;
}

@media (hover: hover) {
  .welcome-right-col:hover {
    border: 1px solid #a78bfa87;
    /* background: rgba(167, 139, 250, 0.08); */
  }
}

.welcome-preview-large {
  flex: 1;
  min-height: 0;
  max-height: 350px;
  aspect-ratio: 3 / 4;
  overflow: hidden;
  border-radius: 0;
  background: #0f172a;
  display: flex;
  align-items: center;
  justify-content: center;
}

.welcome-preview-large img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 0;
}

.welcome-preview-large.pdf-preview-large {
  position: relative;
}

.pdf-thumb {
  position: relative;
}

.pdf-click-overlay {
  position: absolute;
  inset: 0;
  z-index: 1;
  top: 59px;
  cursor: pointer;
}

.pdf-large-object {
  width: 100%;
  height: 100%;
  overflow: hidden;
  border-radius: 0;
}

.pdf-fallback-icon-large {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  height: 100%;
  color: #64748b;
}

.pdf-fallback-label,
.text-fallback-label {
  font-size: 11px;
  color: #94a3b8;
  text-align: center;
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.welcome-preview-large.text-preview-large {
  flex-direction: column;
  gap: 8px;
  color: #64748b;
}

.welcome-preview-name {
  display: block;
  padding: 8px 8px 6px;
  font-size: 11px;
  color: #94a3b8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
  text-align: center;
}

/* Carousel arrows for multi-file preview */
.carousel-arrow {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  z-index: 3;
  background: rgba(15, 23, 42, 0.7);
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 50%;
  color: #e2e8f0;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0;
  transition:
    opacity 0.2s,
    background 0.15s;
  padding: 0;
}

.welcome-right-col:hover .carousel-arrow {
  opacity: 1;
}

.carousel-arrow:hover {
  background: rgba(167, 139, 250, 0.3);
  border-color: rgba(167, 139, 250, 0.5);
}

.carousel-arrow-left {
  left: 6px;
}

.carousel-arrow-right {
  right: 6px;
}

.carousel-dots {
  display: flex;
  gap: 5px;
  justify-content: center;
  padding: 0 8px 8px;
}

.carousel-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(148, 163, 184, 0.3);
  transition: background 0.2s;
}

.carousel-dot.active {
  background: #a78bfa;
}

/* Responsive: mobile/tablet = small thumbs, wide desktop = large right preview */
@media (max-width: 1024px) {
  .welcome-two-col {
    display: block;
  }
  .welcome-right-col {
    display: none;
  }
  .welcome-file-previews-mobile {
    display: flex;
  }

  .action-more-wrap {
    display: flex;
    flex-direction: column;
  }
}

@media (min-width: 1025px) {
  .welcome-file-previews-mobile {
    display: none;
  }
}

/* Welcome suggested questions (inline) */
.welcome-suggested-questions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 14px 0 2px;
}

/* Translation fade: applies to assistant content, user text, and suggested questions.
   Duration matches FADE_MIN_MS in LanguageToggle.vue so cached translations still animate.
   Image-containing blocks are deliberately excluded via :not(:has(img)) so pictures
   remain stable while surrounding text re-renders in the new language. */
.message-content-wrap :deep(.markdown-content) > *:not(:has(img)),
.user-text,
.welcome-suggested-questions {
  transition:
    opacity 200ms ease,
    filter 200ms ease;
}

.message-content-wrap.is-translating :deep(.markdown-content) > *:not(:has(img)),
.user-text.is-translating,
.welcome-suggested-questions.is-translating {
  opacity: 0;
  filter: blur(2px);
}

/* Fade-in for images that arrive dynamically after first render
   (e.g. freshly generated images). The `animate-in` class is only added by
   trackContentImages() for images that were not present on initial mount and
   whose src has not been seen before, so page-load images stay static. */
:deep(.markdown-content img.animate-in) {
  animation: img-fade-in 0.35s ease-out both;
}

@keyframes img-fade-in {
  from {
    opacity: 0;
    transform: scale(0.98);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.welcome-suggested-questions .question-pill {
  margin: 0 6px 8px 0;
}

@keyframes fade-in-right {
  from {
    opacity: 0;
    transform: translateX(8px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.welcome-suggested-questions .question-pill:focus-visible {
  outline: 2px solid rgba(167, 139, 250, 0.6);
  outline-offset: 2px;
}

.suggested-question-markdown {
  white-space: nowrap;
}

.suggested-question-markdown :deep(a) {
  color: inherit;
  text-decoration: underline;
}

.suggested-question-markdown :deep(p) {
  display: inline;
  margin: 0;
}

@media (hover: hover) {
  .welcome-suggested-questions .question-pill:hover {
    background: rgba(167, 139, 250, 0.1);
    border-color: rgba(167, 139, 250, 0.25);
    color: #ddd6fe;
  }
}
.welcome-suggested-questions .question-pill:active {
  background: rgba(167, 139, 250, 0.1);
  border-color: rgba(167, 139, 250, 0.25);
  color: #ddd6fe;
}

/* Upload files row inside first message */
.welcome-upload-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 14px 0 2px;
}

.upload-inline-btn {
  display: inline-flex;
  align-items: center;
  background: rgba(167, 139, 250, 0.12);
  border: 1px solid rgba(167, 139, 250, 0.3);
  color: #c4b5fd;
  border-radius: 10px;
  padding: 4px 14px;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s;
  font-family: inherit;
  height: 26px;
}

@media (hover: hover) {
  .upload-inline-btn:hover {
    background: rgba(167, 139, 250, 0.25);
  }
}
.upload-inline-btn:active {
  background: rgba(167, 139, 250, 0.25);
}

.upload-inline-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.upload-file-name {
  font-size: 12px;
  color: #cbd5e1;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-file-status {
  font-size: 12px;
  color: #a78bfa;
}

.upload-error {
  font-size: 12px;
  color: #fbbf24;
}

:deep(.action-btns-row) {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}

:deep(.action-more-wrap) {
  display: inline-flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}

:deep(.action-visible-row) {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 6px;
}

:deep(.action-overflow-wrap) {
  position: relative;
  display: inline-flex;
  align-items: flex-start;
}

:deep(.action-more-menu) {
  position: fixed;
  left: 0;
  top: 0;
  display: none;
  flex-direction: column;
  gap: 6px;
  z-index: 100;
  min-width: 240px;
  background: #19202b;
  border-radius: 16px;
  padding: 8px;
}

:deep(.action-more-wrap.open .action-more-menu) {
  display: flex;
  animation: fade-in-right 0.2s ease-out;
}

:deep(.action-more-item) {
  margin: 0;
}

/* Colored text markers */
:deep(.text-color-green) {
  color: #86efac;
}
:deep(.text-color-red) {
  color: #fca5a5;
}
:deep(.text-color-yellow) {
  color: #fde047;
}
:deep(.text-color-amber) {
  color: #fcd34d;
}
:deep(.text-color-blue) {
  color: #93c5fd;
}
:deep(.text-color-brown) {
  color: #b08968;
}
:deep(.text-color-purple) {
  color: #c4b5fd;
}
:deep(.text-color-pink) {
  color: #f9a8d4;
}
:deep(.text-color-cyan) {
  color: #67e8f9;
}
:deep(.text-color-orange) {
  color: #fdba74;
}
:deep(.text-color-lime) {
  color: #bef264;
}
:deep(.text-color-rose) {
  color: #fda4af;
}
:deep(.text-color-black) {
  color: #334155;
}
:deep(.text-color-white) {
  color: #f8fafc;
}
:deep(.text-color-gray) {
  color: #94a3b8;
}
:deep(.text-color-teal) {
  color: #2dd4bf;
}
:deep(.text-color-indigo) {
  color: #818cf8;
}
:deep(.text-color-gold) {
  color: #e8b84b;
}
:deep(.text-color-silver) {
  color: #cbd5e1;
}
:deep(.text-color-magenta) {
  color: #e879f9;
}

:deep(.action-btn) {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #94a3b8;
  border-radius: 999px;
  padding: 6px 12px;
  margin: 4px 6px 8px 0;
  font-size: 12px;
  cursor: pointer;
  transition: 0.15s;
}

:deep(.action-btn)::after {
  content: '';
  position: absolute;
  bottom: -8px;
  left: 11px;
  width: 8px;
  height: 7px;
  background: rgba(255, 255, 255, 0.05);
  clip-path: polygon(0 0, 100% 0, 3% 100%);
  pointer-events: none;
  transition: 0.15s;
}

@media (hover: hover) {
  :deep(.action-btn:hover) {
    background: rgba(167, 139, 250, 0.1);
    border-color: rgba(167, 139, 250, 0.25);
    color: #ddd6fe;
  }
  :deep(.action-btn:hover)::after {
    background: rgba(167, 139, 250, 0.1);
  }
}
:deep(.action-btn:active) {
  background: rgba(167, 139, 250, 0.1);
  border-color: rgba(167, 139, 250, 0.25);
  color: #ddd6fe;
}
:deep(.action-btn:active)::after {
  background: rgba(167, 139, 250, 0.1);
}

:deep(.upload-action-btn) {
  background: rgba(56, 189, 248, 0.08);
  border-color: rgba(56, 189, 248, 0.18);
  color: #7dd3fc;
}
:deep(.upload-action-btn)::after {
  display: none;
}
@media (hover: hover) {
  :deep(.upload-action-btn:hover) {
    background: rgba(56, 189, 248, 0.15);
    border-color: rgba(56, 189, 248, 0.3);
    color: #bae6fd;
  }
}

/* Highlight.js code block overrides */
:deep(pre) {
  border-radius: 8px;
  overflow-x: auto;
}
:deep(pre code.hljs) {
  padding: 14px 16px;
  font-size: 13px;
  line-height: 1.5;
  border-radius: 8px;
}

/* Poem / Quote block — decorative centered blockquote */
:deep(.poem-block) {
  text-align: center;
  margin: 20px 0;
  padding: 24px 28px 20px;
  background: rgba(167, 139, 250, 0.04);
  border-radius: 12px;
  border: 1px solid rgba(167, 139, 250, 0.1);
}
:deep(.poem-quote-mark) {
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 48px;
  line-height: 1;
  color: rgba(167, 139, 250, 0.35);
  user-select: none;
}
:deep(.poem-quote-close) {
  margin-top: 4px;
}
:deep(.poem-body) {
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 15.5px;
  line-height: 1.9;
  color: #d1d5db;
  font-style: italic;
  padding: 0 8px;
  letter-spacing: 0.01em;
}

/* Thread reply indicator */
.thread-indicator {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  padding: 4px 10px;
  border-radius: 8px;
  background: rgba(167, 139, 250, 0.08);
  border: 1px solid rgba(167, 139, 250, 0.15);
  cursor: pointer;
  transition:
    background 0.15s,
    border-color 0.15s;
  color: #a78bfa;
  font-size: 12px;
  font-weight: 500;
}

.thread-indicator:hover {
  background: rgba(167, 139, 250, 0.15);
  border-color: rgba(167, 139, 250, 0.3);
}

.thread-indicator .thread-count {
  color: #a78bfa;
}

/* Welcome message title (h2) — larger and more prominent */
.welcome-message .markdown-content h2:first-child {
  font-size: 20px;
  font-weight: 700;
  margin: 0 0 10px;
  color: #f1f5f9;
  line-height: 1.3;
}

/* Fade-in from top for new assistant messages */
@keyframes msg-fade-in-down {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.message.assistant .message-content-wrap.animate-in {
  animation: msg-fade-in-down 0.35s ease-out both;
}

/* Reveal from left-to-right for new user messages */
@keyframes msg-reveal-user-ltr {
  from {
    clip-path: inset(0 100% 0 0);
  }
  to {
    clip-path: inset(0 0 0 0);
  }
}

.message.user .user-text.animate-in {
  animation: msg-reveal-user-ltr 0.111s ease-out both;
}

/* Fade-in for images that arrive after generation (e.g. Pollinations).
   The `animate-in` class is only applied after the initial mount pass, so
   pre-existing conversation images are not animated on page load. Images
   live inside v-html markdown, hence `:deep()`. */
@keyframes img-fade-in {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

:deep(img.animate-in) {
  animation: img-fade-in 0.35s ease-out both;
}
</style>
