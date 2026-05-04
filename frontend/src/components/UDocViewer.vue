<template>
  <div class="udoc-viewer-wrapper">
    <div ref="containerRef" class="udoc-viewer-container" />
    <!-- Mobile close button: floats over the viewer since udoc-viewer has no built-in close -->
    <button
      v-if="showClose"
      class="udoc-close-btn"
      aria-label="Close"
      @click="emit('close')"
    >
      &times;
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { UDocClient } from '@docmentis/udoc-viewer'

const props = withDefaults(
  defineProps<{
    url: string
    page?: number
    highlightText?: string
    showClose?: boolean
  }>(),
  { page: 1, highlightText: '', showClose: false },
)

const emit = defineEmits<{
  close: []
}>()

const containerRef = ref<HTMLDivElement>()
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let client: any = null
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let viewer: any = null

async function navigateAfterLoad() {
  if (!viewer) return
  // Search for highlight text first (highlights the citation text).
  // goToPage is called after search so we always land on the cited page,
  // regardless of where the first search match is located.
  if (props.highlightText) {
    await viewer.search(props.highlightText, { fuzzy: true })
  }
  if (props.page && props.page > 1) {
    viewer.goToPage(props.page)
  }
}

async function initViewer() {
  if (!containerRef.value) return
  try {
    client = await UDocClient.create()
    viewer = await client.createViewer({
      container: containerRef.value,
      theme: 'light',
      zoomMode: 'fit-spread-width',
    })
    await viewer.load(props.url)
    await navigateAfterLoad()
  } catch (err) {
    console.error('UDocViewer init failed:', err)
  }
}

onMounted(() => {
  initViewer()
})

onBeforeUnmount(() => {
  viewer?.destroy()
  client?.destroy()
  viewer = null
  client = null
})

// Reload when source URL changes (e.g. modal reused for different citation)
watch(
  () => props.url,
  async (newUrl, oldUrl) => {
    if (newUrl === oldUrl || !viewer) return
    await viewer.load(newUrl)
    await navigateAfterLoad()
  },
)

// Navigate to a different page without reloading the document
watch(
  () => props.page,
  (newPage) => {
    if (viewer && newPage && newPage > 1) {
      viewer.goToPage(newPage)
    }
  },
)
</script>

<style scoped>
.udoc-viewer-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.udoc-viewer-container {
  width: 100%;
  height: 100%;
  flex: 1;
  min-height: 0;
}

/* Mobile close button — floats in the top-right corner over the viewer */
.udoc-close-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 100;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(4px);
}

.udoc-close-btn:hover {
  background: rgba(0, 0, 0, 0.75);
}
</style>
