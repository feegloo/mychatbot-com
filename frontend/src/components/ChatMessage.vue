<template>
  <div
    class="message-row"
    :class="[msg.role, { 'search-hit': searchHighlighted }]"
    :data-message-id="msg.id || ''"
  >
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
          v-if="canDownloadPdf"
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

      <!-- Generating: image-gen announcement + progressive partial image -->
      <div v-if="msg.role === 'assistant' && msg.generatingImage && !isWelcome">
        <Transition name="generated-image-fade" mode="out-in">
          <GeneratedImageFrame
            v-if="msg.generatingImage && msg.imagePartialDataUrl"
            :key="msg.imagePartialDataUrl"
            :src="msg.imagePartialDataUrl"
            class="image-morph-wrap image-morph image-morph-clickable"
            alt="Generating..."
            @load="onMorphFrameLoad"
            @click="openMorphModal"
          />
        </Transition>
        <div v-if="msg.generatingImage" class="image-generating-label">
          <TextFade :trigger="msg.imageAnnouncement || 'generic'" :disabled="noAnimation">
            <span v-if="msg.imageAnnouncement" style="display: block; text-align: center"
              >🎨 {{ msg.imageAnnouncement }}</span
            >
            <span v-else class="generating-image-please-wait"
              >🎨 Generating image, please wait...</span
            >
          </TextFade>
        </div>
        <div v-if="msg.generatingImage && msg.imageDetailedPrompt" class="image-prompt-detail">
          {{ msg.imageDetailedPrompt }}
        </div>
        <div class="typing-dots"><span></span><span></span><span></span></div>
      </div>

      <div
        v-else-if="msg.role === 'assistant' && imageSwapActive && !isWelcome"
        class="image-swap-wrap"
      >
        <div class="image-swap-shell" :style="imageSwapStyle">
          <Transition name="generated-image-fade">
            <GeneratedImageFrame
              v-if="imageSwapShowNew"
              :key="`swap-new-${imageSwapToSrc}`"
              :src="imageSwapToSrc"
              class="image-swap-image image-swap-new"
              alt="Generated image"
            />
          </Transition>
        </div>
      </div>

      <!-- Welcome message with files: 2-col on desktop, stacked on mobile -->
      <div v-else-if="welcomeHasFiles && msg.role === 'assistant'" class="welcome-two-col">
        <div class="welcome-left-col">
          <div class="message-content-wrap" :class="{ 'is-translating': isTranslating }">
            <TextFade :trigger="assistantFadeTrigger" :disabled="noAnimation">
              <MessageContent
                :content="msg.content"
                :is-welcome="isWelcome"
                :message-id="msg.id"
                :conversation-name="conversationName"
                :file-name="fileName"
                :citations="msg.citations"
                :animate="false"
                @select="$emit('select-question', $event)"
                @select-image-variant="(label, ref) => $emit('select-image-variant', label, ref)"
                @image-click="openImageModal"
                @citation-click="openCitation"
                @upload-trigger="$emit('trigger-upload')"
                @image-loaded="onImageLoad"
                @animated="$emit('message-animated')"
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
        <div class="message-content-wrap" :class="{ 'is-translating': isTranslating }">
          <TextFade :trigger="assistantFadeTrigger" :disabled="noAnimation">
            <MessageContent
              :content="msg.content"
              :is-welcome="isWelcome"
              :message-id="msg.id"
              :conversation-name="conversationName"
              :file-name="fileName"
              :citations="msg.citations"
              :animate="false"
              @select="$emit('select-question', $event)"
              @select-image-variant="(label, ref) => $emit('select-image-variant', label, ref)"
              @image-click="openImageModal"
              @citation-click="openCitation"
              @upload-trigger="$emit('trigger-upload')"
              @image-loaded="onImageLoad"
              @animated="$emit('message-animated')"
            />
          </TextFade>
        </div>
        <div v-if="showTypingDots" class="typing-dots"><span></span><span></span><span></span></div>
      </template>

      <!-- User message -->
      <TextFade v-else :trigger="msg.content" :disabled="noAnimation">
        <span class="user-text" :class="{ 'is-translating': isTranslating }">
          <template v-if="appReady && !noAnimation">
            <template v-for="(tok, i) in userWordTokens" :key="i">
              <span
                v-if="tok.word"
                class="word-reveal"
                :style="{ animationDelay: tok.delay + 'ms' }"
                >{{ tok.word }}</span
              >
              <template v-else>{{ tok.ws }}</template>
            </template>
          </template>
          <template v-else>{{ msg.content }}</template>
        </span>
      </TextFade>

      <!-- Upload row fallback (no welcome files) -->
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
        <span class="thread-count">
          {{ msg.threadReplyCount }} {{ msg.threadReplyCount === 1 ? 'reply' : 'replies' }}
        </span>
      </div>

      <ImageModal
        :visible="modalOpen"
        :src="modalSrc"
        :alt="modalAlt"
        :title="modalTitle"
        @close="modalOpen = false"
      />
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
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
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
import GeneratedImageFrame from './chat/GeneratedImageFrame.vue'

const props = withDefaults(
  defineProps<{
    msg: ChatMessage
    allMessages?: ChatMessage[]
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
    /** When true, triggers the one-shot word-reveal animation for this message.
     *  Only set for newly-arrived messages; cleared by parent after animation. */
    animate?: boolean
    isTranslating?: boolean
    searchHighlighted?: boolean
    searchTerm?: string
  }>(),
  { maxVisibleActions: 2 },
)

const emit = defineEmits<{
  'select-question': [question: string]
  /** Fires when an action with a |ref: image file is clicked for image-to-image generation. */
  'select-image-variant': [label: string, refFileName: string]
  'upload-files': [files: File[]]
  'trigger-upload': []
  'view-threads': [messageId: string]
  /** Fired when an image inside the message bubble has loaded so parents
   *  can re-scroll to bottom. `success` is always true in the rewritten
   *  version since we no longer re-attempt failed image loads. */
  'image-revealed': [success: boolean]
  /** Fired once when the word-reveal animation has run so the parent can
   *  mark this message as animated and prevent replaying on re-mounts. */
  'message-animated': []
}>()

// Use storageConversationId for file URLs (threads point to parent's storage).
const effectiveStorageId = computed(() => props.storageConversationId || props.conversationId)

// Blur intensity for the progressive "morphing" image. Decreases as later
// partial frames arrive so the image visually sharpens into the final
// render. Values picked to roughly match ChatGPT's visible diffusion effect.
// const partialBlurPx = computed(() => {
//   const idx = props.msg.imagePartialIndex ?? 0
//   if (idx <= 0) return 14
//   if (idx === 1) return 6
//   return 2
// })

const MORPH_SWAP_HOLD_MS = 260
const MORPH_SWAP_FAILSAFE_MS = 1800
const lastMorphSrc = ref('')
const lastMorphSize = ref<{ width: number; height: number } | null>(null)
const pendingMorphSwap = ref(false)
const imageSwapActive = ref(false)
const imageSwapShowOld = ref(false)
const imageSwapShowNew = ref(false)
const imageSwapFromSrc = ref('')
const imageSwapToSrc = ref('')
let morphSwapHoldTimer: ReturnType<typeof setTimeout> | null = null
let morphSwapFailsafeTimer: ReturnType<typeof setTimeout> | null = null
let imageSwapRunId = 0

const finalGeneratedImageUrl = computed(() => {
  const content = props.msg.content || ''
  const match = content.match(/!\[[^\]]*\]\(([^)]+)\)/)
  if (!match) return ''
  const target = match[1].trim()
  if (target.startsWith('<')) {
    const end = target.indexOf('>')
    return end > 1 ? target.slice(1, end) : ''
  }
  return target.split(/\s+/)[0] || ''
})

const finalGeneratedImageTitle = computed(() => {
  const content = props.msg.content || ''
  const altMatch = content.match(/!\[([^\]]*)\]\(([^)]+)\)/)
  const markdownAlt = altMatch?.[1]?.trim() || ''
  if (markdownAlt) return markdownAlt
  if (props.msg.imageTitle?.trim()) return props.msg.imageTitle.trim()
  const announcementTitle = (props.msg.imageAnnouncement || '')
    .replace(/^Generating:\s*/i, '')
    .trim()
  return announcementTitle
})

const imageSwapStyle = computed(() => {
  const size = lastMorphSize.value
  if (!size) return undefined
  return {
    width: `${size.width}px`,
    height: `${size.height}px`,
  }
})

function clearMorphSwapTimers() {
  if (morphSwapHoldTimer) {
    clearTimeout(morphSwapHoldTimer)
    morphSwapHoldTimer = null
  }
  if (morphSwapFailsafeTimer) {
    clearTimeout(morphSwapFailsafeTimer)
    morphSwapFailsafeTimer = null
  }
}

function resetMorphSnapshot() {
  lastMorphSrc.value = ''
  lastMorphSize.value = null
}

function finishImageSwap() {
  clearMorphSwapTimers()
  imageSwapActive.value = false
  imageSwapShowOld.value = false
  imageSwapShowNew.value = false
  imageSwapFromSrc.value = ''
  imageSwapToSrc.value = ''
  imageSwapRunId += 1
}

function preloadImage(src: string) {
  return new Promise<void>((resolve, reject) => {
    const img = new window.Image()
    img.onload = () => resolve()
    img.onerror = () => reject(new Error('failed to preload swap target'))
    img.src = src
  })
}

async function startImageSwap(fromSrc: string, toSrc: string) {
  imageSwapRunId += 1
  const runId = imageSwapRunId
  clearMorphSwapTimers()
  imageSwapFromSrc.value = fromSrc
  imageSwapToSrc.value = toSrc
  imageSwapShowOld.value = true
  imageSwapShowNew.value = false
  imageSwapActive.value = true
  morphSwapFailsafeTimer = setTimeout(finishImageSwap, MORPH_SWAP_FAILSAFE_MS)

  try {
    await preloadImage(toSrc)
    if (!imageSwapActive.value || imageSwapRunId !== runId) return
    imageSwapShowNew.value = true
    imageSwapShowOld.value = false
    morphSwapHoldTimer = setTimeout(finishImageSwap, MORPH_SWAP_HOLD_MS)
  } catch {
    if (!imageSwapActive.value || imageSwapRunId !== runId) return
    finishImageSwap()
  }
}

function onMorphFrameLoad(event: Event) {
  const el = event.target as HTMLImageElement
  if (el.currentSrc) {
    lastMorphSrc.value = el.currentSrc
  }
  const rect = el.getBoundingClientRect()
  if (rect.width > 0 && rect.height > 0) {
    lastMorphSize.value = {
      width: Math.round(rect.width),
      height: Math.round(rect.height),
    }
  }
}

function maybeStartMorphSwap() {
  if (!pendingMorphSwap.value || props.msg.generatingImage) return
  if (!lastMorphSrc.value || !finalGeneratedImageUrl.value) return
  pendingMorphSwap.value = false
  startImageSwap(lastMorphSrc.value, finalGeneratedImageUrl.value)
}

watch(
  () => props.msg.imagePartialDataUrl,
  (src) => {
    if (!src) return
    lastMorphSrc.value = src
  },
)

watch(
  () => props.msg.generatingImage,
  (isGenerating, wasGenerating) => {
    if (isGenerating) {
      pendingMorphSwap.value = false
      finishImageSwap()
      // Start each generation with a clean snapshot so a previous message
      // cannot accidentally drive a swap when this run has no partial frame.
      resetMorphSnapshot()
      return
    }
    if (wasGenerating && lastMorphSrc.value) {
      pendingMorphSwap.value = true
      void nextTick(() => {
        maybeStartMorphSwap()
      })
      return
    }

    // No partial image was ever observed for this generation.
    // Fall through to normal final-image rendering with no swap stage.
    pendingMorphSwap.value = false
    finishImageSwap()
  },
)

watch(finalGeneratedImageUrl, () => {
  maybeStartMorphSwap()
})

onBeforeUnmount(() => {
  clearMorphSwapTimers()
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
// --- TextFade trigger for assistant messages ------------------------------
// During streaming the message has no id yet. Using `msg.content` as the
// key would remount MessageContent on every streamed token, causing
// animation chaos and UI jank. A stable `'streaming'` key prevents those
// remounts; when streaming completes and `msg.id` is set the key switches
// to the full content, triggering exactly one remount + transition.
// Subsequent content changes (translations) are then keyed on content so
// the fade transition plays correctly.
const assistantFadeTrigger = computed(() => (props.msg.id ? props.msg.content : 'streaming'))

const showTypingDots = computed(() => {
  if (props.msg.role !== 'assistant' || props.isWelcome) return false
  if (props.asking && !props.msg.id) return true
  if (props.msg.generatingImage) return true
  return !(props.msg.content ?? '').trim()
})

// --- Word-reveal staggering for user message ------------------------------
// User text is plain (no markdown) so we split up-front in the template
// instead of walking the DOM like we do for assistant content. Delay is
// clamped so pasting a wall of text still finishes inside ~2 s.
const USER_REVEAL_MAX_MS = 500
type UserWordToken =
  | { word: string; ws?: undefined; delay: number }
  | { ws: string; word?: undefined; delay?: undefined }
const userWordTokens = computed<UserWordToken[]>(() => {
  if (props.msg.role !== 'user') return []
  const parts = (props.msg.content ?? '').split(/(\s+)/).filter(Boolean)
  const words = parts.filter((p) => !/^\s+$/.test(p)).length
  if (!words) return []
  // Same sqrt easing as wordReveal.ts: slow start → accelerating reveal.
  const easedDelay = (i: number) =>
    words <= 1 ? 0 : Math.round(USER_REVEAL_MAX_MS * Math.sqrt(i / (words - 1)))
  let i = 0
  return parts.map((p) => (/^\s+$/.test(p) ? { ws: p } : { word: p, delay: easedDelay(i++) }))
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
    props.msg.role === 'assistant' && !!props.msg.content && !props.msg.content.includes('[quiz:'),
)

async function downloadMessagePdf() {
  const title = props.conversationName || 'chatrag'
  try {
    const { printContentAsPdf, printAssistantMessagesAsPdf } = await import('../utils/printPdf')

    // Welcome-message PDF should export all assistant answers in the conversation.
    if (props.isWelcome) {
      const assistantMessages = (props.allMessages || [])
        .filter((m) => m.role === 'assistant' && !!m.content?.trim() && !m.content.includes('[quiz:'))
        .map((m) => ({ content: m.content }))

      if (assistantMessages.length > 0) {
        await printAssistantMessagesAsPdf(assistantMessages, `${title} - assistant messages`, {
          conversationId: effectiveStorageId.value,
        })
        return
      }
    }

    await printContentAsPdf(props.msg.content, title, { conversationId: effectiveStorageId.value })
  } catch (err) {
    console.error('PDF generation failed:', err)
    alert('PDF generation failed. Please reload the page and try again.')
  }
}

// --- Modals ---------------------------------------------------------------
const modalOpen = ref(false)
const modalSrc = ref('')
const modalAlt = ref('')
const modalTitle = ref('')
// True when modal was opened by clicking the morph/partial image. While set,
// the modal src tracks new partials and the final generated image live.
const morphModalActive = ref(false)

function openImageModal(src: string, alt: string) {
  modalSrc.value = src
  modalAlt.value = alt
  modalTitle.value = alt
  morphModalActive.value = false
  modalOpen.value = true
}

function openMorphModal() {
  const src = props.msg.imagePartialDataUrl || lastMorphSrc.value
  if (!src) return
  modalSrc.value = src
  modalAlt.value = finalGeneratedImageTitle.value || props.msg.imageAnnouncement || 'Generating...'
  modalTitle.value = finalGeneratedImageTitle.value || props.msg.imageAnnouncement || ''
  morphModalActive.value = true
  modalOpen.value = true
}

// Keep modal src in sync as new morph partials arrive
watch(
  () => props.msg.imagePartialDataUrl,
  (newSrc) => {
    if (newSrc && morphModalActive.value && modalOpen.value) {
      modalSrc.value = newSrc
    }
  },
)

// Advance modal to the final generated image when ready
watch(finalGeneratedImageUrl, (newUrl) => {
  if (newUrl && morphModalActive.value && modalOpen.value) {
    modalSrc.value = newUrl
    modalAlt.value = finalGeneratedImageTitle.value || 'Generated image'
    modalTitle.value = finalGeneratedImageTitle.value
    morphModalActive.value = false
  }
})

watch(modalOpen, (open) => {
  if (!open) morphModalActive.value = false
})

const previewOpen = ref(false)
const previewCitation = ref<NonNullable<ChatMessage['citations']>[number]>()

function openCitation(idx: number) {
  const citation = props.msg.citations?.[idx]
  if (citation) {
    previewCitation.value = citation
    previewOpen.value = true
    return
  }
  // Welcome messages store citations as { _uploadedFileNames } on the backend,
  // so the citations array is empty. Fall back to opening the Nth file (1-based
  // source index) from the files associated with this message.
  const file = props.files?.[idx]
  if (file) {
    previewCitation.value = {
      fileName: file.originalName,
      chunkId: '',
      text: '',
      page: 1,
    }
    previewOpen.value = true
  }
}

// --- Image citations (clickable thumbnails row) ---------------------------
type CitationEntry = NonNullable<ChatMessage['citations']>[number]
type ImageCitationInfo = { url: string; section?: string; imageName: string }

const imageCitations = computed<ImageCitationInfo[]>(() => {
  if (!props.msg.citations) return []

  // Collect imageNames already displayed in earlier messages to avoid repetition
  const shownBefore = new Set<string>()
  if (props.allMessages) {
    const currentIdx = props.allMessages.findIndex(
      (m) => (m.id && props.msg.id ? m.id === props.msg.id : m === props.msg),
    )
    const preceding = currentIdx > 0 ? props.allMessages.slice(0, currentIdx) : []
    for (const prev of preceding) {
      if (prev.role === 'assistant' && prev.citations) {
        for (const c of prev.citations) {
          if ((c as CitationEntry & { imageName?: string }).imageName) {
            shownBefore.add((c as CitationEntry & { imageName: string }).imageName)
          }
        }
      }
    }
  }

  return props.msg.citations
    .filter(
      (c): c is CitationEntry & { imageName: string } =>
        !!c.imageName && !shownBefore.has(c.imageName),
    )
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

// Clicking a welcome-message file preview opens ImageModal for images,
// SourcePreviewModal for PDFs and other file types.
function openFilePreview(file: FileInfo) {
  if (file.mimeType?.startsWith('image/')) {
    openImageModal(getFileUrl(file), file.originalName)
    return
  }
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
    opacity 150ms ease,
    filter 150ms ease;
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

.welcome-message :deep(.markdown-content) {
  margin: 0;
}

/* Image generating label. */
.image-generating-label {
  margin: 6px 0 8px;
  font-size: 13px;
  color: #c4b5fd;
}

.image-prompt-detail {
  display: none;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.4;
  color: rgba(255, 255, 255, 0.72);
  white-space: pre-wrap;
}

.image-morph-clickable {
  cursor: pointer;
}

/* Fade-in for the first partial frame. Paired with the v-if above so the
   wrap mounts at opacity 0 and eases to 1, giving the morph a smooth
   "reveal" instead of popping in at full brightness. */
.generated-image-fade-enter-active,
.generated-image-fade-leave-active {
  transition: opacity 320ms ease-in-out;
}

.generated-image-fade-enter-from,
.generated-image-fade-leave-to {
  opacity: 0;
}

.generated-image-fade-enter-to,
.generated-image-fade-leave-from {
  opacity: 1;
}

.image-swap-wrap {
  margin: 6px 0 8px;
}

.image-swap-shell {
  position: relative;
  width: min(70vh, 420px);
  max-width: 100%;
  aspect-ratio: 1 / 1;
  border-radius: 12px;
  overflow: hidden;
  background: rgba(167, 139, 250, 0.08);
}

.image-swap-image {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
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
:deep(.text-color-green) {
  color: #86efac;
}
:deep(.text-color-red) {
  color: #fca5a5;
}
:deep(.text-color-yellow) {
  color: #fde047;
}
:deep(.text-color-blue) {
  color: #93c5fd;
}
:deep(.text-color-purple) {
  color: #c4b5fd;
}
:deep(.text-color-orange) {
  color: #fdba74;
}
:deep(.text-color-gold) {
  color: #e8b84b;
}
:deep(.text-color-pink) {
  color: #f9a8d4;
}
:deep(.text-color-gray) {
  color: #94a3b8;
}

/* Ingredient measurement unit badges (volume = blue, weight = orange). */
:deep(li .munit) {
  display: inline-block;
  padding: 0 5px;
  border-radius: 4px;
  font-size: 0.76em;
  font-weight: 700;
  vertical-align: baseline;
  letter-spacing: 0.03em;
  line-height: 1.6;
  user-select: text;
}
:deep(li .munit-vol) {
  background: rgba(147, 197, 253, 0.15);
  color: #93c5fd;
  border: 1px solid rgba(147, 197, 253, 0.3);
}
:deep(li .munit-wt) {
  background: rgba(253, 186, 116, 0.15);
  color: #fdba74;
  border: 1px solid rgba(253, 186, 116, 0.3);
}
</style>
