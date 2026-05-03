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

          <!-- Source text document (non-PDF, non-SVG only) -->
          <div v-if="!isPdf && !isSvg" class="source-modal-doc">
            <div class="source-modal-doc-header">
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
                class="source-modal-doc-icon"
              >
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
              </svg>
              <span class="source-modal-doc-name">{{ cleanFileName(citation.fileName) }}</span>
              <button
                v-if="isMobile"
                class="source-modal-doc-close"
                aria-label="Close"
                @click="$emit('close')"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
            <div class="source-modal-doc-body">
              <div v-if="fetchLoading" class="source-modal-doc-text source-modal-doc-text--loading">
                Loading…
              </div>
              <!-- eslint-disable-next-line vue/no-v-html -->
              <div v-else class="source-modal-doc-text" v-html="linkify(displayText)" />
            </div>
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


      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { getStorageUrl } from '../api'
import { cleanFileName, linkify } from '../utils/text'
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
const RASTER_EXTENSIONS = new Set(['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', '.tif', '.heic', '.avif'])
const isRasterImage = computed(() => {
  const lower = props.citation.fileName.toLowerCase()
  return [...RASTER_EXTENSIONS].some((ext) => lower.endsWith(ext))
})

const isMobile = computed(() => /iPhone|iPad|iPod|Android/i.test(navigator.userAgent))

const pdfBaseUrl = computed(() => getStorageUrl(props.conversationId, props.citation.fileName))

function openFullPdf() {
  window.open(pdfBaseUrl.value, '_blank', 'noopener')
}

// When opened for a text file (non-PDF) with no pre-fetched citation text,
// fetch the raw file content from storage so the modal is not empty.
const fetchedText = ref('')
const fetchLoading = ref(false)

// Use immediate: true so the watcher fires on first mount — the component
// mounts with visible=true when v-if and :visible are both set in the same
// tick (openCitation / openFilePreview), so a lazy watch would never see the
// false→true transition and the fallback fetch would never run.
watch(
  () => props.visible,
  async (open) => {
    // Never try to fetch raw binary files — raster images and SVGs are either
    // shown via <img> or have indexed text in citation.text already.
    if (!open || isPdf.value || isSvg.value || isRasterImage.value || props.citation.text) {
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
  { immediate: true },
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

.source-modal-content--text {
  width: min(900px, 80vw);
  height: calc(100vh - 20px);
  background: #fff;
  border-radius: 4px;
  box-shadow: 0 12px 60px rgba(0, 0, 0, 0.6);
}

.source-modal-doc {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.source-modal-doc-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  background: #f3f4f6;
  border-bottom: 1px solid #e5e7eb;
  border-radius: 4px 4px 0 0;
  flex-shrink: 0;
}

.source-modal-doc-icon {
  flex-shrink: 0;
  color: #6b7280;
}

.source-modal-doc-name {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  color: #374151;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.source-modal-doc-close {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: none;
  background: transparent;
  color: #6b7280;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}

.source-modal-doc-close:hover {
  background: #e5e7eb;
}

.source-modal-doc-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 48px 60px;
  background: #fff;
  border-radius: 0 0 4px 4px;
}

.source-modal-doc-text {
  font-size: 15px;
  color: #1a1a1a;
  font-style: normal;
  font-weight: 400;
  white-space: pre-wrap;
  line-height: 1.8;
  word-break: break-word;
}

.source-modal-doc-text--loading {
  color: #9ca3af;
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
    height: 90vh;
    width: 92vw;
    max-height: none;
    margin: auto;
    border-radius: 8px;
    flex: none;
    align-self: center;
  }

  .source-modal-doc-body {
    padding: 24px 20px;
  }
}
</style>
