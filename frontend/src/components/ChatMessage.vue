<template>
  <div class="message-row" :class="msg.role">
    <div class="message" :class="[msg.role, { 'welcome-message': isWelcome }]">
      <strong>{{ senderLabel }}</strong>

      <!-- Action buttons (share / PDF / upload-more) — assistant messages only -->
      <div v-if="msg.role === 'assistant' && msg.content" class="msg-actions">
        <AppButton
          v-if="isFirstMessage && canUpload"
          class="msg-action-btn"
          title="Upload more files"
          @click="triggerUpload"
        >
          <svg
width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
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
v-if="!shareCopied" width="14" height="14" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="18" cy="5" r="3" />
            <circle cx="6" cy="12" r="3" />
            <circle cx="18" cy="19" r="3" />
            <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
            <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
          </svg>
          <svg
v-else width="14" height="14" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
          {{ shareCopied ? 'Link copied!' : 'Share' }}
        </AppButton>
        <AppButton
          v-if="canDownloadPdf"
          class="msg-action-btn"
          title="Download PDF"
          @click="downloadMessagePdf"
        >
          <svg
width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
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

      <!-- Generating: image-gen announcement + progressive partial image -->
      <div v-if="msg.role === 'assistant' && !msg.content && !msg.id && !isWelcome">
        <div v-if="msg.generatingImage" class="image-generating-label">
          <TextFade :trigger="msg.imageAnnouncement || 'generic'">
            <span v-if="msg.imageAnnouncement">🎨 {{ msg.imageAnnouncement }}</span>
            <span v-else>🎨 Generating image, please wait...</span>
          </TextFade>
        </div>
        <Transition name="image-morph-fade">
          <div v-if="msg.generatingImage && msg.imagePartialDataUrl" class="image-morph-wrap">
            <img
              :src="msg.imagePartialDataUrl"
              :style="{ filter: `blur(${partialBlurPx}px)` }"
              class="image-morph"
              alt="Generating..."
            />
          </div>
        </Transition>
        <div class="typing-dots"><span></span><span></span><span></span></div>
      </div>

      <!-- Welcome message with files: 2-col on desktop, stacked on mobile -->
      <div v-else-if="welcomeHasFiles && msg.role === 'assistant'" class="welcome-two-col">
        <div class="welcome-left-col">
          <div
            class="message-content-wrap"
            :class="{ 'is-translating': isTranslating }"
          >
            <TextFade :trigger="msg.content">
              <MessageContent
                :content="msg.content"
                :is-welcome="isWelcome"
                :message-id="msg.id"
                :conversation-name="conversationName"
                :file-name="fileName"
                :citations="msg.citations"
                @select="$emit('select-question', $event)"
                @image-click="openImageModal"
                @citation-click="openCitation"
                @upload-trigger="$emit('trigger-upload')"
                @image-loaded="onImageLoad"
              />
            </TextFade>
          </div>
          <div
            v-if="isFirstMessage && canUpload && (selectedUploadFiles.length || uploadError)"
            class="welcome-upload-row"
          >
            <template v-if="selectedUploadFiles.length">
              <span v-for="file in selectedUploadFiles" :key="file.name" class="upload-file-name">
                {{ file.name }}
              </span>
              <span v-if="uploadingFiles" class="upload-file-status"><UploadingDots /></span>
            </template>
            <span v-if="uploadError" class="upload-error">{{ uploadError }}</span>
          </div>
        </div>
        <div class="welcome-right-col">
          <PreviewFiles
            :files="files ?? []"
            :conversation-id="effectiveStorageId"
            :get-url="getFileUrl"
            @open="openFilePreview"
          />
        </div>
      </div>

      <!-- Regular assistant content -->
      <template v-else-if="msg.role === 'assistant'">
        <div
          class="message-content-wrap"
          :class="{ 'is-translating': isTranslating }"
        >
          <TextFade :trigger="msg.content">
            <MessageContent
              :content="msg.content"
              :is-welcome="isWelcome"
              :message-id="msg.id"
              :conversation-name="conversationName"
              :file-name="fileName"
              :citations="msg.citations"
              @select="$emit('select-question', $event)"
              @image-click="openImageModal"
              @citation-click="openCitation"
              @upload-trigger="$emit('trigger-upload')"
              @image-loaded="onImageLoad"
            />
          </TextFade>
        </div>
        <div v-if="!msg.id && !isWelcome && msg.generatingImage" class="typing-dots">
          <span></span><span></span><span></span>
        </div>
      </template>

      <!-- User message -->
      <TextFade v-else :trigger="msg.content">
        <span class="user-text" :class="{ 'is-translating': isTranslating }">
          <template v-if="appReady">
            <template v-for="(tok, i) in userWordTokens" :key="i">
              <span
                v-if="tok.word"
                class="word-reveal"
                :style="{ animationDelay: tok.delay + 'ms' }"
              >{{ tok.word }}</span>
              <template v-else>{{ tok.ws }}</template>
            </template>
          </template>
          <template v-else>{{ msg.content }}</template>
        </span>
      </TextFade>

      <!-- Upload row fallback (no welcome files) -->
      <div
        v-if="
          isFirstMessage && canUpload && !welcomeHasFiles &&
          (selectedUploadFiles.length || uploadError)
        "
        class="welcome-upload-row"
      >
        <template v-if="selectedUploadFiles.length">
          <span v-for="file in selectedUploadFiles" :key="file.name" class="upload-file-name">
            {{ file.name }}
          </span>
          <span v-if="uploadingFiles" class="upload-file-status"><UploadingDots /></span>
        </template>
        <span v-if="uploadError" class="upload-error">{{ uploadError }}</span>
      </div>

      <!-- Image citations (clickable thumbnails) -->
      <div v-if="imageCitations.length" class="citation-images">
        <div
          v-for="(img, idx) in imageCitations"
          :key="idx"
          class="citation-image-thumb"
          @click="openImageModal(img.url, img.section || 'Image')"
        >
          <img :src="img.url" :alt="img.section || 'Image'" loading="lazy" @load="onImageLoad" />
          <span class="citation-image-label">{{ img.section || 'Image' }}</span>
        </div>
      </div>

      <!-- Thread reply indicator -->
      <div
        v-if="msg.threadReplyCount"
        class="thread-indicator"
        @click="$emit('view-threads', msg.id!)"
      >
        <svg
width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
        <span class="thread-count">
          {{ msg.threadReplyCount }} {{ msg.threadReplyCount === 1 ? 'reply' : 'replies' }}
        </span>
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
/**
 * Single chat message bubble. Thin wrapper — delegates content rendering to
 * `chat/MessageContent.vue` (markdown + tokens + quiz/mermaid + click
 * delegation) and welcome-file previews to `chat/PreviewFiles.vue`. Owns
 * the modals (image lightbox, source preview) and the file-upload bridge
 * exposed to parents via `defineExpose`.
 *
 * Public API preserved from the previous 2234-line implementation so all
 * parent pages (ConversationPage, SharedMessagePage, HomePage) work
 * without modification.
 */
import { computed, ref } from 'vue'
import type { ChatMessage, ConversationStatus } from '../api'
import { getStorageUrl } from '../api'
import { getUserId } from '../utils/fingerprint'
import { appReady } from '../composables/appReady'
import AppButton from './AppButton.vue'
import TextFade from './TextFade.vue'
import ImageModal from './ImageModal.vue'
import SourcePreviewModal from './SourcePreviewModal.vue'
import UploadingDots from './UploadingDots.vue'
import MessageContent from './chat/MessageContent.vue'
import PreviewFiles from './chat/PreviewFiles.vue'

const props = withDefaults(
  defineProps<{
    msg: ChatMessage
    asking: boolean
    conversationId: string
    storageConversationId?: string
    isWelcome?: boolean
    isFirstMessage?: boolean
    canUpload?: boolean
    files?: ConversationStatus['files']
    /** Reserved for future per-message visible-action overrides. The new
     *  MessageContent applies fixed limits per spec (welcome 3+2 / regular 2+1). */
    maxVisibleActions?: number
    conversationName?: string
    fileName?: string
    isThread?: boolean
    noAnimation?: boolean
    isTranslating?: boolean
  }>(),
  { maxVisibleActions: 2 },
)

const emit = defineEmits<{
  'select-question': [question: string]
  'upload-files': [files: File[]]
  'trigger-upload': []
  'view-threads': [messageId: string]
  /** Fired when an image inside the message bubble has loaded so parents
   *  can re-scroll to bottom. `success` is always true in the rewritten
   *  version since we no longer re-attempt failed image loads. */
  'image-revealed': [success: boolean]
}>()

// Use storageConversationId for file URLs (threads point to parent's storage).
const effectiveStorageId = computed(() => props.storageConversationId || props.conversationId)

// Blur intensity for the progressive "morphing" image. Decreases as later
// partial frames arrive so the image visually sharpens into the final
// render. Values picked to roughly match ChatGPT's visible diffusion effect.
const partialBlurPx = computed(() => {
  const idx = props.msg.imagePartialIndex ?? 0
  if (idx <= 0) return 14
  if (idx === 1) return 6
  return 2
})

const senderLabel = computed(() => {
  if (props.msg.role === 'assistant') return 'Assistant'
  if (props.isThread && props.msg.userId) {
    const myId = getUserId()
    if (myId !== null && props.msg.userId === myId) return 'You'
    return `user${props.msg.userId}`
  }
  return 'You'
})

// --- Word-reveal staggering for user message ------------------------------
// User text is plain (no markdown) so we split up-front in the template
// instead of walking the DOM like we do for assistant content. Delay is
// clamped so pasting a wall of text still finishes inside ~2 s.
const USER_REVEAL_MAX_MS = 2000
type UserWordToken = { word: string; ws?: undefined; delay: number } | { ws: string; word?: undefined; delay?: undefined }
const userWordTokens = computed<UserWordToken[]>(() => {
  if (props.msg.role !== 'user') return []
  const parts = (props.msg.content ?? '').split(/(\s+)/).filter(Boolean)
  const words = parts.filter((p) => !/^\s+$/.test(p)).length
  if (!words) return []
  // Same sqrt easing as wordReveal.ts: slow start → accelerating reveal.
  const easedDelay = (i: number) =>
    words <= 1 ? 0 : Math.round(USER_REVEAL_MAX_MS * Math.sqrt(i / (words - 1)))
  let i = 0
  return parts.map((p) =>
    /^\s+$/.test(p)
      ? { ws: p }
      : { word: p, delay: easedDelay(i++) },
  )
})

// --- Upload-more-files state ----------------------------------------------
const uploadInput = ref<HTMLInputElement | null>(null)
const selectedUploadFiles = ref<File[]>([])
const uploadingFiles = ref(false)
const uploadError = ref('')

const welcomeHasFiles = computed(() => props.isWelcome && (props.files?.length ?? 0) > 0)

function onUploadFilesChange(event: Event) {
  const target = event.target as HTMLInputElement
  const allFiles = Array.from(target.files || [])
  const videoFiles = allFiles.filter((f) => f.type.startsWith('video/'))
  const validFiles = allFiles.filter((f) => !f.type.startsWith('video/'))
  uploadError.value = videoFiles.length ? 'Video files are not supported.' : ''
  selectedUploadFiles.value = validFiles
  if (validFiles.length) emit('upload-files', validFiles)
}

function triggerUpload() {
  uploadInput.value?.click()
}

function resetUploadState(error?: string) {
  selectedUploadFiles.value = []
  uploadingFiles.value = false
  uploadError.value = error || ''
  if (uploadInput.value) uploadInput.value.value = ''
}

function setUploading(val: boolean) {
  uploadingFiles.value = val
}

defineExpose({ resetUploadState, setUploading, triggerUpload })

// --- Share + PDF ----------------------------------------------------------
const shareCopied = ref(false)
function shareMessage() {
  const url = props.msg.id
    ? `${window.location.origin}/m/${props.msg.id}`
    : `${window.location.origin}/c/${props.conversationId}`
  navigator.clipboard.writeText(url)
  shareCopied.value = true
  setTimeout(() => {
    shareCopied.value = false
  }, 2000)
}

const canDownloadPdf = computed(
  () =>
    props.msg.role === 'assistant' &&
    !!props.msg.content &&
    !props.msg.content.includes('[quiz:'),
)

async function downloadMessagePdf() {
  const title = props.conversationName || 'chatrag'
  try {
    const { printContentAsPdf } = await import('../utils/printPdf')
    await printContentAsPdf(props.msg.content, title)
  } catch (err) {
    console.error('PDF generation failed:', err)
    alert('PDF generation failed. Please reload the page and try again.')
  }
}

// --- Modals ---------------------------------------------------------------
const modalOpen = ref(false)
const modalSrc = ref('')
const modalAlt = ref('')

function openImageModal(src: string, alt: string) {
  modalSrc.value = src
  modalAlt.value = alt
  modalOpen.value = true
}

const previewOpen = ref(false)
const previewCitation = ref<NonNullable<ChatMessage['citations']>[number]>()

function openCitation(idx: number) {
  const citation = props.msg.citations?.[idx]
  if (!citation) return
  previewCitation.value = citation
  previewOpen.value = true
}

// --- Image citations (clickable thumbnails row) ---------------------------
type CitationEntry = NonNullable<ChatMessage['citations']>[number]
type ImageCitationInfo = { url: string; section?: string; imageName: string }

const imageCitations = computed<ImageCitationInfo[]>(() => {
  if (!props.msg.citations) return []
  return props.msg.citations
    .filter((c): c is CitationEntry & { imageName: string } => !!c.imageName)
    .map((c) => ({
      url: getStorageUrl(effectiveStorageId.value, c.imageName),
      section: c.section,
      imageName: c.imageName,
    }))
})

function onImageLoad() {
  emit('image-revealed', true)
}

// --- Welcome file previews (PreviewFiles helpers) -------------------------
type FileInfo = NonNullable<ConversationStatus['files']>[number]

function getFileUrl(file: FileInfo) {
  return getStorageUrl(effectiveStorageId.value, file.originalName)
}

// Clicking a welcome-message file preview opens the same modal used by
// citation buttons. PDFs land on page 1; non-PDFs fall back to the text
// preview layout with no highlighted quote.
function openFilePreview(file: FileInfo) {
  previewCitation.value = {
    fileName: file.originalName,
    chunkId: '',
    text: '',
    page: 1,
  }
  previewOpen.value = true
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
  font-family: inherit;
  transition:
    background 0.15s,
    color 0.15s,
    border-color 0.15s;
}
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

/* Inline source citation buttons (rendered by renderMarkdown). */
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
  font-family: inherit;
}
:deep(.inline-source-icon) {
  font-size: 9px;
}

/* Image citations row. */
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
  max-width: 140px;
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

/* Welcome 2-column layout. */
.welcome-two-col {
  display: flex;
  gap: 20px;
  min-height: 160px;
}
.welcome-left-col {
  flex: 1;
  min-width: 0;
}
.welcome-right-col {
  flex-shrink: 0;
  width: 240px;
  display: flex;
  align-items: flex-start;
}
@media (max-width: 1024px) {
  .welcome-two-col {
    flex-direction: column;
  }
  .welcome-right-col {
    width: 100%;
  }
}

/* Translation fade (text only, leaves images stable). */
.message-content-wrap :deep(.markdown-content) > *:not(:has(img)),
.user-text {
  transition:
    opacity 200ms ease,
    filter 200ms ease;
}
.message-content-wrap.is-translating :deep(.markdown-content) > *:not(:has(img)),
.user-text.is-translating {
  opacity: 0;
  filter: blur(2px);
}

/* Upload row inside first message. */
.welcome-upload-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 14px 0 2px;
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

/* Thread reply indicator. */
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
  color: #a78bfa;
  font-size: 12px;
  font-weight: 500;
  transition:
    background 0.15s,
    border-color 0.15s;
}
.thread-indicator:hover {
  background: rgba(167, 139, 250, 0.15);
  border-color: rgba(167, 139, 250, 0.3);
}
.thread-count {
  color: #a78bfa;
}

/* Welcome message title (first H2) — larger and more prominent. */
.welcome-message :deep(.markdown-content h2:first-child) {
  font-size: 20px;
  font-weight: 700;
  margin: 0 0 10px;
  color: #f1f5f9;
  line-height: 1.3;
}

/* Image generating label. */
.image-generating-label {
  margin: 6px 0 8px;
  font-size: 13px;
  color: #c4b5fd;
}

/* Progressive (morphing) partial image while OpenAI streams the diffusion
   intermediates. Grows to match the final image width (capped at 512px to
   keep the bubble from dominating the viewport); the blur value is driven
   inline by the partial frame index so each new frame sharpens. */
.image-morph-wrap {
  margin: 6px 0 8px;
  max-width: min(70vh, 420px);
  border-radius: 12px;
  overflow: hidden;
  background: rgba(167, 139, 250, 0.08);
  animation: image-morph-pulse 2.2s ease-in-out infinite;
}
.image-morph {
  display: block;
  width: 100%;
  height: auto;
  transform: scale(1.02);
  transition: filter 600ms ease-out;
  will-change: filter;
}
@keyframes image-morph-pulse {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(167, 139, 250, 0.25);
  }
  50% {
    box-shadow: 0 0 24px 2px rgba(167, 139, 250, 0.35);
  }
}

/* Fade-in for the first partial frame. Paired with the v-if above so the
   wrap mounts at opacity 0 and eases to 1, giving the morph a smooth
   "reveal" instead of popping in at full brightness. */
.image-morph-fade-enter-active {
  transition: opacity 700ms ease-out;
}
.image-morph-fade-enter-from {
  opacity: 0;
}
.image-morph-fade-enter-to {
  opacity: 1;
}

/* Highlight.js code block sizing. */
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

/* Poem block. */
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
:deep(.poem-body) {
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 15.5px;
  line-height: 1.9;
  color: #d1d5db;
  font-style: italic;
  padding: 0 8px;
  letter-spacing: 0.01em;
}

/* Colored text markers. */
:deep(.text-color-green) { color: #86efac; }
:deep(.text-color-red) { color: #fca5a5; }
:deep(.text-color-yellow) { color: #fde047; }
:deep(.text-color-blue) { color: #93c5fd; }
:deep(.text-color-purple) { color: #c4b5fd; }
:deep(.text-color-orange) { color: #fdba74; }
:deep(.text-color-gold) { color: #e8b84b; }
:deep(.text-color-teal) { color: #2dd4bf; }
:deep(.text-color-pink) { color: #f9a8d4; }
:deep(.text-color-gray) { color: #94a3b8; }
</style>
