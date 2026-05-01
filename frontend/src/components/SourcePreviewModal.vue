<template>
  <Teleport to="body">
    <div v-if="visible" class="source-modal-overlay" @click.self="$emit('close')">
      <div class="source-modal-inner">
        <div class="source-modal-content" :class="{ 'source-modal-content--text': !isPdf && !isSvg }">
          <!-- PDF preview: custom pdfjs viewer with text layer + highlight -->
          <PdfPageViewer
            v-if="isPdf"
            :url="pdfBaseUrl"
            :page="citation.page ?? 1"
            :highlight-text="citation.text"
            :show-close="isMobile"
            :show-open-pdf="isMobile && isOwner"
            @close="$emit('close')"
            @open-pdf="openFullPdf"
          />

          <!-- SVG image preview -->
          <div v-else-if="isSvg" class="source-modal-svg">
            <img :src="pdfBaseUrl" :alt="citation.fileName" class="source-modal-svg-img" />
          </div>

          <!-- Source text quote (non-PDF, non-SVG only) -->
          <div v-if="!isPdf && !isSvg" class="source-modal-quote">
            <div class="source-modal-quote-label">Source text</div>
            <div v-if="fetchLoading" class="source-modal-quote-text" style="opacity: 0.5">
              Loading…
            </div>
            <!-- eslint-disable-next-line vue/no-v-html -->
            <div v-else class="source-modal-quote-text" v-html="linkify(displayText)" />
          </div>
        </div>

        <!-- Desktop close: sits to the right of the PDF, not on top of it -->
        <button
          v-if="!isMobile"
          class="source-modal-close-desktop"
          aria-label="Close"
          @click="$emit('close')"
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.5"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>

        <!-- Non-PDF, non-SVG mobile close (text quote modal) -->
        <button
          v-if="isMobile && !isPdf && !isSvg"
          class="source-modal-close-mobile-text"
          aria-label="Close"
          @click="$emit('close')"
        >
          &times;
        </button>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { getStorageUrl } from '../api'
import { linkify } from '../utils/text'
import PdfPageViewer from './PdfPageViewer.vue'

const props = withDefaults(
  defineProps<{
    visible: boolean
    citation: {
      fileName: string
      chunkId: string
      text: string
      section?: string
      page?: number | null
      imageName?: string
    }
    conversationId: string
    isOwner?: boolean
  }>(),
  { isOwner: true },
)

defineEmits<{
  close: []
}>()

const isPdf = computed(() => props.citation.fileName.toLowerCase().endsWith('.pdf'))
const isSvg = computed(() => props.citation.fileName.toLowerCase().endsWith('.svg'))

const isMobile = computed(() => /iPhone|iPad|iPod|Android/i.test(navigator.userAgent))

const pdfBaseUrl = computed(() => getStorageUrl(props.conversationId, props.citation.fileName))

function openFullPdf() {
  window.open(pdfBaseUrl.value, '_blank', 'noopener')
}

// When opened for a text file (non-PDF) with no pre-fetched citation text,
// fetch the raw file content from storage so the modal is not empty.
const fetchedText = ref('')
const fetchLoading = ref(false)

watch(
  () => props.visible,
  async (open) => {
    if (!open || isPdf.value || isSvg.value || props.citation.text) {
      fetchedText.value = ''
      return
    }
    fetchLoading.value = true
    try {
      const res = await fetch(pdfBaseUrl.value)
      fetchedText.value = res.ok ? await res.text() : ''
    } catch {
      fetchedText.value = ''
    } finally {
      fetchLoading.value = false
    }
  },
)

const displayText = computed(() => props.citation.text || fetchedText.value)
</script>

<style scoped>
.source-modal-svg {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  padding: 24px;
  box-sizing: border-box;
}

.source-modal-svg-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 8px;
  background: white;
}

.source-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

/* Flex row: PDF content + close button side by side on desktop */
.source-modal-inner {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  cursor: default;
}

.source-modal-content {
  position: relative;
  width: min(900px, 80vw);
  height: calc(100vh - 20px);
  margin: 10px 0;
  background: transparent;
  border-radius: 0;
  box-shadow: none;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Desktop close: white circle to the right of the PDF */
.source-modal-close-desktop {
  flex-shrink: 0;
  align-self: flex-start;
  margin-top: 10px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: rgba(255, 255, 255, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.28);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  transition: background 0.15s;
}

@media (hover: hover) {
  .source-modal-close-desktop:hover {
    background: rgba(255, 255, 255, 0.28);
  }
}

.source-modal-close-desktop:active {
  background: rgba(255, 255, 255, 0.35);
}

/* Mobile close for non-PDF text quote modal */
.source-modal-close-mobile-text {
  position: fixed;
  top: 12px;
  right: 12px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.45);
  color: #e2e8f0;
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.source-modal-quote {
  padding: 16px 20px 20px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.source-modal-quote-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
  margin-bottom: 6px;
}

.source-modal-quote-text {
  font-size: 14px;
  color: #94a3b8;
  font-style: italic;
  white-space: pre-wrap;
  line-height: 1.5;
}

.source-modal-content--text {
  width: min(600px, 80vw);
  height: auto;
  max-height: 80vh;
  background: #1e1033;
  border: 1px solid rgba(124, 58, 237, 0.3);
  border-radius: 12px;
}

@media (max-width: 768px) {
  .source-modal-overlay {
    align-items: stretch;
    justify-content: stretch;
  }

  .source-modal-inner {
    flex: 1;
    width: 100%;
  }

  .source-modal-content {
    width: 100%;
    height: 100%;
    margin: 0;
    border-radius: 0;
    flex: 1;
  }

  .source-modal-content--text {
    height: auto;
    max-height: 60vh;
    width: 92vw;
    margin: auto;
    border-radius: 12px;
    flex: none;
    align-self: center;
  }
}
</style>
