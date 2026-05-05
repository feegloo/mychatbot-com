<script setup lang="ts">
/**
 * File carousel for welcome-message attachments. Picks the right leaf
 * component per mime type and handles prev/next navigation when there
 * are 2+ files.
 *
 * `files` accepts the rich `ConversationStatus['files']` shape so we
 * preserve originalName, mimeType, and id without re-deriving from URL.
 */
import { computed, ref } from 'vue'
import type { ConversationStatus } from '../../api'
import PreviewImg from './PreviewImg.vue'
import PreviewPdf from './PreviewPdf.vue'
import PreviewText from './PreviewText.vue'

type File = NonNullable<ConversationStatus['files']>[number]

const props = defineProps<{
  files: File[]
  conversationId: string
  getUrl: (file: File) => string
}>()
const emit = defineEmits<{ open: [file: File] }>()

const index = ref(0)
const current = computed<File | undefined>(() => props.files[index.value] ?? props.files[0])
const hasMultiple = computed(() => props.files.length > 1)
const currentIsPdf = computed(() => (current.value ? isDocument(current.value) : false))

function isImage(f: File) {
  return f.mimeType?.startsWith('image/') ?? false
}
const DOCUMENT_MIME_TYPES = new Set([
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
])
function isDocument(f: File) {
  return DOCUMENT_MIME_TYPES.has(f.mimeType ?? '')
}

function next(event: Event) {
  event.stopPropagation()
  index.value = (index.value + 1) % props.files.length
}
function prev(event: Event) {
  event.stopPropagation()
  index.value = (index.value - 1 + props.files.length) % props.files.length
}
</script>

<template>
  <div v-if="current" class="preview-files" :class="{ 'preview-files--pdf': currentIsPdf }">
    <button v-if="hasMultiple" class="arrow arrow-left" title="Previous" @click="prev">
      <svg
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.5"
        stroke-linecap="round"
      >
        <polyline points="15 18 9 12 15 6" />
      </svg>
    </button>

    <div class="preview-stage">
      <PreviewImg
        v-if="isImage(current)"
        :url="getUrl(current)"
        :name="current.originalName"
        @open="emit('open', current!)"
      />
      <PreviewPdf
        v-else-if="isDocument(current)"
        :conversation-id="props.conversationId"
        :file-name="current.originalName"
        :name="current.originalName"
        @open="emit('open', current!)"
      />
      <PreviewText v-else :name="current.originalName" @open="emit('open', current!)" />
    </div>

    <button v-if="hasMultiple" class="arrow arrow-right" title="Next" @click="next">
      <svg
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.5"
        stroke-linecap="round"
      >
        <polyline points="9 18 15 12 9 6" />
      </svg>
    </button>

    <span class="name">{{ current.originalName }}</span>

    <div v-if="hasMultiple" class="dots">
      <span v-for="(_, i) in files" :key="i" class="dot" :class="{ active: i === index }"></span>
    </div>
  </div>
</template>

<style scoped>
.preview-files {
  height: 100%;
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.preview-stage {
  width: 100%;
  min-height: 90%;
}

@media (max-width: 768px) {
  .preview-files--pdf {
    gap: 0;
  }

  .preview-files--pdf .preview-stage {
    min-height: 360px;
  }

  .preview-files--pdf .name {
    margin: -6px 0 0;
  }
}

.arrow {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  z-index: 2;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.45);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.arrow:hover {
  background: rgba(0, 0, 0, 0.65);
}
.arrow-left {
  left: 8px;
}
.arrow-right {
  right: 8px;
}
.name {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.6);
  text-align: center;
  max-width: 100%;
  overflow: hidden;
  margin: 8px 0;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dots {
  display: flex;
  gap: 4px;
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
}
.dot.active {
  background: rgba(255, 255, 255, 0.7);
}
</style>
