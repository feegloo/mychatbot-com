<script setup lang="ts">
/**
 * Document preview tile (PDF, DOCX, PPTX). Uses <object> for PDFs so the
 * browser's native PDF viewer handles the thumbnail; shows a file-type icon
 * directly for other supported document formats. Parent handles click-to-open.
 */
import { ref, watch, computed } from 'vue'
import { resolveStorageUrl } from '../../api'

const props = defineProps<{ conversationId: string; fileName: string; name: string }>()
const emit = defineEmits<{ open: [] }>()

const embedUrl = ref<string | null>(null)

const isPdf = computed(() => props.fileName.toLowerCase().endsWith('.pdf'))

watch(
  () => [props.conversationId, props.fileName] as const,
  async ([conversationId, fileName]) => {
    embedUrl.value = null
    if (!conversationId || !fileName || !isPdf.value) return
    try {
      embedUrl.value = await resolveStorageUrl(conversationId, fileName)
    } catch (err) {
      console.warn('Failed to resolve PDF preview URL:', err)
    }
  },
  { immediate: true },
)
</script>

<template>
  <div class="preview-pdf" @click="emit('open')">
    <object v-if="embedUrl" :data="embedUrl" type="application/pdf" class="preview-pdf-obj">
      <div class="fallback">
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
        </svg>
        <span>{{ name }}</span>
      </div>
    </object>
    <div v-else class="fallback">
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
      </svg>
      <span>{{ name }}</span>
    </div>
    <div class="preview-pdf-overlay"></div>
  </div>
</template>

<style scoped>
.preview-pdf {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  cursor: pointer;
}
.preview-pdf-obj {
  width: 100%;
  pointer-events: none;
  padding-bottom: 10px;
  /* Shift the object up to hide Chrome's native 56px grey toolbar */
  margin-top: -56px;
  height: 451px; /* 395 + 56 to fill the container after the shift */
}
.preview-pdf-overlay {
  position: absolute;
  /* top: 56px; */
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
}
.fallback {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 100%;
  color: rgba(255, 255, 255, 0.6);
  font-size: 12px;
  text-align: center;
  padding: 8px;
}
</style>
