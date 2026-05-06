<template>
  <div class="udoc-viewer-wrapper">
    <div ref="containerRef" class="udoc-viewer-container" :class="{ 'udoc-viewer-container--hidden': loading }" />
    <!-- Loader overlay shown until document is loaded and navigated to target page -->
    <div v-if="loading" class="udoc-loader">
      <div class="udoc-loader-spinner" />
    </div>
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
import type { ThemeMode } from '@docmentis/udoc-viewer'

const THEME_STORAGE_KEY = 'udoc-viewer-theme'
const ZOOM_SNAP_MARGIN = 0.05
// Maximum length of text used for in-viewer search / text selection.
// Shorter phrases are more reliable for fuzzy matching; we take the first
// sentence (up to a period/question-mark) that is at least 20 chars long,
// capped at 120 chars. If no sentence boundary is found, we use the first
// 120 chars of the text.
const SEARCH_TEXT_MAX = 120

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
const loading = ref(true)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let client: any = null
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let viewer: any = null
let themeObserver: MutationObserver | null = null

function loadSavedTheme(): ThemeMode {
  const saved = localStorage.getItem(THEME_STORAGE_KEY)
  return saved === 'dark' || saved === 'system' ? (saved as ThemeMode) : 'light'
}

// Persist theme whenever the viewer's dark class toggles (user clicked theme button)
function setupThemeObserver() {
  if (!containerRef.value || !viewer) return
  themeObserver = new MutationObserver(() => {
    if (viewer) {
      localStorage.setItem(THEME_STORAGE_KEY, viewer.theme)
    }
  })
  themeObserver.observe(containerRef.value, {
    subtree: true,
    attributes: true,
    attributeFilter: ['class'],
  })
}

/**
 * Extract a short, distinctive search phrase from citation text.
 * Takes the first sentence (up to `.` or `?` or `!`) that is at least
 * 20 chars long, capped at SEARCH_TEXT_MAX. Falls back to the first
 * SEARCH_TEXT_MAX characters of the text.
 */
function extractSearchPhrase(text: string): string {
  const cleaned = text.trim()
  // Try to find a sentence boundary between 20 and SEARCH_TEXT_MAX chars
  const match = cleaned.slice(0, SEARCH_TEXT_MAX + 60).match(/^(.{20,}?[.!?])(?:\s|$)/)
  if (match && match[1].length <= SEARCH_TEXT_MAX) {
    return match[1].trim()
  }
  return cleaned.slice(0, SEARCH_TEXT_MAX).trim()
}

async function navigateAfterLoad() {
  if (!viewer) return
  const page = props.page ?? 1
  let navigatedToMatch = false

  if (props.highlightText) {
    const phrase = extractSearchPhrase(props.highlightText)
    // Restrict to the cited page (0-based) — faster than scanning the whole doc
    // and avoids highlighting the same phrase on unrelated pages.
    const matches = await viewer.search(phrase, {
      fuzzy: true,
      pageRange: [page - 1, page - 1],
    })
    if (matches.length > 0) {
      // Scroll the matched text to the center of the viewport so it's immediately visible.
      viewer.setSearchActiveIndex(0, { scrollAlignment: 'center' })
      navigatedToMatch = true
    }
  }

  // Fall back to top-of-page navigation when search found no match
  // (e.g. the PDF text differs enough that fuzzy matching still fails).
  if (!navigatedToMatch && page > 1) {
    viewer.goToPage(page)
  }

  // Hide loader only after navigation is complete so user never sees page 1 flash
  loading.value = false
}

function snapZoomIfNear100() {
  if (!viewer) return
  const zoom = viewer.zoom
  if (Math.abs(zoom - 1) <= ZOOM_SNAP_MARGIN) {
    viewer.setZoom(1)
  }
}

async function initViewer() {
  if (!containerRef.value) return
  loading.value = true
  try {
    client = await UDocClient.create()
    viewer = await client.createViewer({
      container: containerRef.value,
      theme: loadSavedTheme(),
      zoomMode: 'fit-spread-width',
      // Hide the pointer/hand/zoom tool buttons (the arrow cursor button on the left)
      disableViewTools: true,
    })
    await viewer.load(props.url)
    await navigateAfterLoad()
    // Snap to 100% if auto-calculated effective zoom is within ±5%.
    // Use double rAF so the viewer's layout pass has time to compute effectiveZoom.
    requestAnimationFrame(() => requestAnimationFrame(snapZoomIfNear100))
    setupThemeObserver()
  } catch (err) {
    console.error('UDocViewer init failed:', err)
    loading.value = false
  }
}

onMounted(() => {
  initViewer()
})

onBeforeUnmount(() => {
  themeObserver?.disconnect()
  themeObserver = null
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
    loading.value = true
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

.udoc-viewer-container--hidden {
  visibility: hidden;
}

.udoc-loader {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-surface, #1a1a1a);
  z-index: 10;
}

.udoc-loader-spinner {
  width: 36px;
  height: 36px;
  border: 3px solid rgba(255, 255, 255, 0.15);
  border-top-color: rgba(255, 255, 255, 0.7);
  border-radius: 50%;
  animation: udoc-spin 0.7s linear infinite;
}

@keyframes udoc-spin {
  to { transform: rotate(360deg); }
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

/* Hide the view settings (layout/scroll/rotation) button in the bottom floating toolbar */
:deep(.udoc-view-mode-menu) {
  display: none !important;
}
</style>
