<script setup lang="ts">
/**
 * PDF preview tile. Uses <object> so the browser's native PDF viewer
 * handles zoom/scroll; falls back to an icon when the browser rejects
 * inline PDF embedding. Parent handles click-to-open.
 *
 * The embed URL is resolved asynchronously via `/storage/:id/:name/url`
 * so `<object>` points directly at the final origin (for GCS: the signed
 * storage.googleapis.com URL). If we embedded the same-origin proxy URL
 * instead, the browser would refuse to follow the cross-origin redirect
 * from inside the PDF viewer frame ("Unsafe attempt to load URL ... from
 * frame with URL ...") and the preview would fail to render.
 */
import { ref, watch } from 'vue'
import { resolveStorageUrl } from '../../api'

const props = defineProps<{ conversationId: string; fileName: string; name: string }>()
const emit = defineEmits<{ open: [] }>()

const embedUrl = ref<string | null>(null)

watch(
  () => [props.conversationId, props.fileName] as const,
  async ([conversationId, fileName]) => {
    embedUrl.value = null
    if (!conversationId || !fileName) return
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
  height: 100%;
  pointer-events: none;
}
.preview-pdf-overlay {
  position: absolute;
  inset: 0;
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
