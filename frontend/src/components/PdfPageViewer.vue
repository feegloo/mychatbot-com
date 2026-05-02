<template>
  <div ref="rootEl" class="pdf-page-viewer" @wheel="onWheel">
    <div v-if="loading" class="pdf-page-loading">Loading…</div>
    <div v-if="error" class="pdf-page-error">{{ error }}</div>
    <div
      v-show="!loading && !error"
      ref="pagesContainer"
      class="pdf-pages-container"
      @touchstart.passive="onTouchStart"
      @touchmove="onTouchMove"
      @touchend="onTouchEnd"
      @touchcancel="onTouchEnd"
    >
      <div
        v-for="pg in pageNumbers"
        :key="pg"
        :ref="(el) => setPageRef(pg, el as HTMLElement)"
        class="pdf-page-wrapper"
        :data-page="pg"
        :style="wrapperStyle(pg)"
      >
        <canvas :ref="(el) => setCanvasRef(pg, el as HTMLCanvasElement)" class="pdf-page-canvas" />
        <div :ref="(el) => setTextRef(pg, el as HTMLElement)" class="textLayer" />
      </div>
    </div>
    <div class="pdf-toolbar" aria-label="PDF controls">
      <button
        v-if="showOpenPdf"
        class="pdf-tool-btn pdf-tool-btn--text"
        @click="emit('openPdf')"
      >
        Otwórz PDF
      </button>
      <span v-if="showOpenPdf" class="pdf-toolbar-divider" aria-hidden="true" />

      <button class="pdf-tool-btn" aria-label="Previous page" :disabled="currentPage <= 1" @click="goToPrevPage">
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2.5"
        >
          <polyline points="15 18 9 12 15 6" />
        </svg>
      </button>
      <span class="pdf-page-info" aria-live="polite" aria-atomic="true">{{ currentPage }} / {{ totalPages }}</span>
      <button class="pdf-tool-btn" aria-label="Next page" :disabled="currentPage >= totalPages" @click="goToNextPage">
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2.5"
        >
          <polyline points="9 18 15 12 9 6" />
        </svg>
      </button>

      <template v-if="showClose">
        <span class="pdf-toolbar-divider" aria-hidden="true" />
        <button class="pdf-tool-btn pdf-tool-btn--text" aria-label="Zamknij" @click="emit('close')">
          Zamknij ✕
        </button>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, nextTick, computed } from 'vue'
import { getDocument, GlobalWorkerOptions, renderTextLayer } from 'pdfjs-dist'
import type { PDFDocumentProxy, PDFPageProxy, RenderTask } from 'pdfjs-dist'
import {
  isMobileUserAgent,
  estimatePageHeight,
  detectSwipe,
  pointDistance,
  clampScale,
  computePinchScale,
  LruSet,
} from './PdfPageViewer.utils'
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.js?url'

GlobalWorkerOptions.workerSrc = pdfWorkerUrl

// pdfjs-dist runtime assets are copied under the app's Vite base path at build
// time (see vite.config.ts). Providing these URLs enables full image decoding
// (JPEG2000/JBIG2 via wasm, ICC color profiles), CJK cmaps, and standard font
// fallbacks — without them embedded images in PDFs may fail to render.
const PDFJS_BASE_URL = import.meta.env.BASE_URL.endsWith('/')
  ? import.meta.env.BASE_URL
  : `${import.meta.env.BASE_URL}/`
const PDFJS_CMAP_URL = `${PDFJS_BASE_URL}pdfjs/cmaps/`
const PDFJS_STANDARD_FONT_URL = `${PDFJS_BASE_URL}pdfjs/standard_fonts/`

const props = withDefaults(
  defineProps<{
    url: string
    page?: number
    highlightText?: string
    showClose?: boolean
    showOpenPdf?: boolean
  }>(),
  { page: 1, highlightText: '', showClose: false, showOpenPdf: false },
)

const emit = defineEmits<{
  close: []
  openPdf: []
}>()

const rootEl = ref<HTMLElement | null>(null)
const pagesContainer = ref<HTMLElement | null>(null)
const loading = ref(true)
const error = ref('')
const totalPages = ref(0)
const currentPage = ref(1)
const scale = ref(1)

const canvasRefs = new Map<number, HTMLCanvasElement>()
const textRefs = new Map<number, HTMLElement>()
const pageRefs = new Map<number, HTMLElement>()
const pageProxies = new Map<number, PDFPageProxy>()
// Non-reactive map for O(1) lookups; `aspectVersion` is bumped on each mutation
// so reactive consumers (e.g. `wrapperStyle`) re-evaluate.
const pageAspectRatios = new Map<number, number>() // width / height
const aspectVersion = ref(0)
const activeRenderTasks = new Map<number, RenderTask>()
// Pages currently inside the observer margin. `renderPage` re-checks this set
// after every `await` to avoid rendering pages the user has scrolled past.
const intersectingPages = new Set<number>()

function setPageAspect(pageNum: number, aspect: number) {
  const prev = pageAspectRatios.get(pageNum)
  if (prev === aspect) return
  pageAspectRatios.set(pageNum, aspect)
  aspectVersion.value++
}

const isMobile = isMobileUserAgent()
const MAX_RENDERED_PAGES = isMobile ? 6 : 10
const renderedLru = new LruSet<number>(MAX_RENDERED_PAGES)
const HORIZONTAL_PADDING = 0 // container has no side padding; pages span full width
// Don't re-render the canvas on every pinch delta — only commit when the
// scale has moved by at least this much, to keep pinch fluid.
const PINCH_RERENDER_THRESHOLD = 0.15
// A touch is treated as a tap only if it stays within this much movement
// and ends within this many milliseconds (used for double-tap detection).
const MAX_TAP_MOVEMENT_PX = 10
const MAX_TAP_DURATION_MS = 300
const DOUBLE_TAP_WINDOW_MS = 300

let pdfDoc: PDFDocumentProxy | null = null
let highlightDone = false
const defaultAspectRatio = ref(1 / Math.SQRT2) // A4 portrait placeholder until first page arrives
const containerWidth = ref(600)
let observer: IntersectionObserver | null = null
let resizeObserver: ResizeObserver | null = null
let highlightTargetPage = -1

const pageNumbers = computed(() => {
  const list: number[] = []
  for (let i = 1; i <= totalPages.value; i++) list.push(i)
  return list
})

function setCanvasRef(pg: number, el: HTMLCanvasElement | null) {
  if (el) canvasRefs.set(pg, el)
  else canvasRefs.delete(pg)
}
function setTextRef(pg: number, el: HTMLElement | null) {
  if (el) textRefs.set(pg, el)
  else textRefs.delete(pg)
}
function setPageRef(pg: number, el: HTMLElement | null) {
  if (el) {
    pageRefs.set(pg, el)
    observer?.observe(el)
  } else {
    const prev = pageRefs.get(pg)
    if (prev) observer?.unobserve(prev)
    pageRefs.delete(pg)
  }
}

function wrapperStyle(pg: number): Record<string, string> {
  // Touch `aspectVersion` so wrapperStyle re-evaluates when per-page aspect
  // ratios are refined during rendering.
  void aspectVersion.value
  const aspect = pageAspectRatios.get(pg) ?? defaultAspectRatio.value
  const height = estimatePageHeight(aspect, containerWidth.value, HORIZONTAL_PADDING, scale.value)
  return {
    height: `${height}px`,
    // Skip layout/paint of offscreen pages for free.
    'content-visibility': 'auto',
    'contain-intrinsic-size': `${height}px`,
  }
}

// Token used to guard against out-of-order results when props.url changes
// while a previous load is still in-flight.
let loadToken = 0

function resetViewerState() {
  try {
    pdfDoc?.destroy()
  } catch (destroyErr) {
    console.warn('PDF destroy on reset failed:', destroyErr)
  }
  pdfDoc = null
  pageProxies.clear()
  canvasRefs.clear()
  textRefs.clear()
  pageRefs.clear()
  totalPages.value = 0
  currentPage.value = 1
  highlightDone = false
  error.value = ''
  loading.value = true
}

async function loadPdf() {
  const myToken = ++loadToken
  resetViewerState()
  try {
    const task = getDocument({
      url: props.url,
      cMapUrl: PDFJS_CMAP_URL,
      cMapPacked: true,
      standardFontDataUrl: PDFJS_STANDARD_FONT_URL,
    })
    const doc = await task.promise
    // Abandon this result if another load started in the meantime
    if (myToken !== loadToken) {
      doc.destroy()
      return
    }
    pdfDoc = doc
    totalPages.value = pdfDoc.numPages
    currentPage.value = Math.min(Math.max(props.page, 1), pdfDoc.numPages)
    highlightTargetPage = currentPage.value

    await nextTick()
    if (myToken !== loadToken) return
    containerWidth.value = rootEl.value?.clientWidth || 600

    // Use the first page's aspect ratio to seed placeholder sizes for every
    // page. Individual pages are refined when they actually render.
    try {
      const firstPage = await getPageProxy(1)
      const vp = firstPage.getViewport({ scale: 1 })
      defaultAspectRatio.value = vp.width / vp.height
      setPageAspect(1, defaultAspectRatio.value)
    } catch (e) {
      console.warn('PDF first-page probe failed:', e)
    }

    loading.value = false
    await nextTick()

    setupObservers()

    // Scroll to the initial target page (usually the cited page for the
    // SourcePreviewModal) before the observer kicks off rendering.
    if (currentPage.value > 1) {
      const el = pageRefs.get(currentPage.value)
      if (el && pagesContainer.value) {
        pagesContainer.value.scrollTop = el.offsetTop
      }
    }
  } catch (err) {
    if (myToken !== loadToken) return
    console.error('PDF load failed:', err, { url: props.url, page: props.page })
    error.value = 'Could not load PDF'
    loading.value = false
  }
}

function setupObservers() {
  const container = pagesContainer.value
  if (!container) return

  observer = new IntersectionObserver(onIntersect, {
    root: container,
    // Render pages up to ~2 screens above/below the viewport, unload beyond.
    rootMargin: '200% 0px 200% 0px',
    threshold: 0,
  })
  for (const el of pageRefs.values()) observer.observe(el)

  resizeObserver = new ResizeObserver(onContainerResize)
  resizeObserver.observe(container)
}

function onContainerResize() {
  const container = pagesContainer.value
  if (!container) return
  const newWidth = container.clientWidth
  if (newWidth === containerWidth.value) return
  containerWidth.value = newWidth
  invalidateRenders()
}

function onIntersect(entries: IntersectionObserverEntry[]) {
  for (const entry of entries) {
    const el = entry.target as HTMLElement
    const pg = Number(el.dataset.page)
    if (!pg) continue
    if (entry.isIntersecting) {
      intersectingPages.add(pg)
      void renderPage(pg)
    } else {
      intersectingPages.delete(pg)
      unloadPage(pg)
    }
  }
  updateCurrentPageFromScroll()
}

async function getPageProxy(pageNum: number): Promise<PDFPageProxy> {
  if (pageProxies.has(pageNum)) return pageProxies.get(pageNum)!
  const page = await pdfDoc!.getPage(pageNum)
  pageProxies.set(pageNum, page)
  if (!pageAspectRatios.has(pageNum)) {
    const vp = page.getViewport({ scale: 1 })
    setPageAspect(pageNum, vp.width / vp.height)
  }
  return page
}

function unloadPage(pageNum: number) {
  // Cancel in-flight render if any.
  const task = activeRenderTasks.get(pageNum)
  if (task) {
    try {
      task.cancel()
    } catch {
      /* ignore */
    }
    activeRenderTasks.delete(pageNum)
  }

  intersectingPages.delete(pageNum)

  const canvas = canvasRefs.get(pageNum)
  if (canvas) {
    canvas.width = 0
    canvas.height = 0
    canvas.removeAttribute('style')
    canvas.dataset.scaleKey = ''
  }
  const textDiv = textRefs.get(pageNum)
  if (textDiv) {
    textDiv.innerHTML = ''
    textDiv.removeAttribute('style')
  }

  renderedLru.delete(pageNum)
  const proxy = pageProxies.get(pageNum)
  if (proxy) {
    try {
      proxy.cleanup()
    } catch {
      /* ignore */
    }
  }
}

/**
 * Cancel all in-flight render tasks and clear their scale keys. Called on
 * scale or container-width changes so old renders can't "complete" onto a
 * canvas that's now stale and mark it as up-to-date with the old key.
 */
function invalidateRenders() {
  for (const task of activeRenderTasks.values()) {
    try {
      task.cancel()
    } catch {
      /* ignore */
    }
  }
  activeRenderTasks.clear()
  for (const canvas of canvasRefs.values()) canvas.dataset.scaleKey = ''
  scheduleRenderVisible()
}

function currentScaleKey(): string {
  return `rendered-${scale.value}-${containerWidth.value}`
}

async function renderPage(pageNum: number) {
  const canvas = canvasRefs.get(pageNum)
  const textDiv = textRefs.get(pageNum)
  if (!canvas || !textDiv || !pdfDoc) return

  const scaleKey = currentScaleKey()
  if (canvas.dataset.scaleKey === scaleKey) {
    renderedLru.touch(pageNum)
    return
  }

  // Bail out if a render is already in flight for this page.
  if (activeRenderTasks.has(pageNum)) return

  const page = await getPageProxy(pageNum)
  // Page could have been unloaded or scrolled out of the render window while
  // we awaited the page proxy.
  if (!canvasRefs.has(pageNum) || !intersectingPages.has(pageNum)) return
  // Scale/width may have changed during the await — try again with the new key.
  if (currentScaleKey() !== scaleKey) {
    void renderPage(pageNum)
    return
  }

  const unscaledVp = page.getViewport({ scale: 1 })
  setPageAspect(pageNum, unscaledVp.width / unscaledVp.height)

  const baseScale = (containerWidth.value - HORIZONTAL_PADDING) / unscaledVp.width
  const effectiveScale = baseScale * scale.value
  const clampedDevicePixelRatio = Math.min(window.devicePixelRatio || 1, isMobile ? 1.5 : 2)
  const viewport = page.getViewport({ scale: effectiveScale * clampedDevicePixelRatio })
  const displayViewport = page.getViewport({ scale: effectiveScale })

  canvas.width = viewport.width
  canvas.height = viewport.height
  canvas.style.width = displayViewport.width + 'px'
  canvas.style.height = displayViewport.height + 'px'

  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const task = page.render({ canvasContext: ctx, viewport })
  activeRenderTasks.set(pageNum, task)
  try {
    await task.promise
  } catch (err) {
    // Cancellations are expected when the user scrolls past a page mid-render
    // or when scale/width changes invalidate this render.
    const name = (err as { name?: string } | null)?.name
    if (name !== 'RenderingCancelledException') {
      console.warn(`PDF page ${pageNum} render cancelled/failed:`, err)
    }
    if (activeRenderTasks.get(pageNum) === task) activeRenderTasks.delete(pageNum)
    return
  }
  if (activeRenderTasks.get(pageNum) === task) activeRenderTasks.delete(pageNum)

  // Drop this render if the viewer state changed during rendering; otherwise
  // we'd mark the canvas as up-to-date with a stale scale/width.
  if (
    !canvasRefs.has(pageNum) ||
    !intersectingPages.has(pageNum) ||
    currentScaleKey() !== scaleKey
  ) {
    void renderPage(pageNum)
    return
  }

  // Text layer
  textDiv.innerHTML = ''
  textDiv.style.width = displayViewport.width + 'px'
  textDiv.style.height = displayViewport.height + 'px'
  const scaleFactor = displayViewport.scale
  textDiv.style.setProperty('--total-scale-factor', String(scaleFactor))

  try {
    const textContent = await page.getTextContent()
    // getTextContent can race with unload/scale changes too.
    if (!textRefs.has(pageNum) || currentScaleKey() !== scaleKey) return
    const textLayer = renderTextLayer({
      textContentSource: textContent,
      container: textDiv,
      viewport: displayViewport,
    })
    await textLayer.promise
  } catch (e) {
    console.warn(`PDF page ${pageNum} text layer failed:`, e)
  }

  canvas.dataset.scaleKey = scaleKey

  // LRU bookkeeping — evict the least-recently-rendered page if over capacity.
  const evicted = renderedLru.touch(pageNum)
  if (evicted !== undefined && evicted !== pageNum) unloadPage(evicted)

  // Highlight cited text once, on the target page, after it renders.
  if (pageNum === highlightTargetPage && props.highlightText && !highlightDone) {
    await nextTick()
    highlightTextInLayer(textDiv)
  }
}

function scheduleRenderVisible() {
  // Re-render currently intersecting pages (canvases are cleared on resize/zoom).
  for (const pg of renderedLru.values()) {
    void renderPage(pg)
  }
  // Also hit pages currently in the viewport that aren't in the LRU yet.
  const container = pagesContainer.value
  if (!container) return
  const top = container.scrollTop
  const bottom = top + container.clientHeight
  for (const [pg, el] of pageRefs.entries()) {
    const elTop = el.offsetTop
    const elBottom = elTop + el.offsetHeight
    if (elBottom > top && elTop < bottom) void renderPage(pg)
  }
}

/** Normalize text for fuzzy comparison */
function normalizeText(s: string): string {
  return s
    .replace(/[\r\n]+/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/[""]/g, '"')
    .replace(/['']/g, "'")
    .replace(/[–—]/g, '-')
    .trim()
    .toLowerCase()
}

/**
 * Find contiguous text layer spans matching the source highlight text
 * and apply highlight styling + scroll into view.
 */
function highlightTextInLayer(textDiv: HTMLElement) {
  const sourceText = normalizeText(props.highlightText)
  if (!sourceText || sourceText.length < 10) return

  const spans = Array.from(textDiv.querySelectorAll('span')) as HTMLElement[]
  if (!spans.length) return

  const items: { span: HTMLElement; start: number; text: string }[] = []
  let concat = ''
  for (const span of spans) {
    const text = span.textContent || ''
    items.push({ span, start: concat.length, text })
    concat += normalizeText(text) + ' '
  }
  const fullText = concat.trimEnd()

  const sourceWords = sourceText.split(/\s+/)
  const searchPrefix = sourceWords.slice(0, Math.min(8, sourceWords.length)).join(' ')
  const startIdx = fullText.indexOf(searchPrefix)
  if (startIdx === -1) {
    const shortPrefix = sourceWords.slice(0, Math.min(4, sourceWords.length)).join(' ')
    const shortIdx = fullText.indexOf(shortPrefix)
    if (shortIdx === -1) return
    applyHighlight(items, shortIdx, shortIdx + sourceText.length, fullText)
    return
  }

  applyHighlight(items, startIdx, startIdx + sourceText.length, fullText)
}

function applyHighlight(
  items: { span: HTMLElement; start: number; text: string }[],
  matchStart: number,
  matchEnd: number,
  fullText: string,
) {
  const effectiveEnd = Math.min(matchEnd, fullText.length)
  let firstHighlighted: HTMLElement | null = null

  for (const item of items) {
    const spanEnd = item.start + normalizeText(item.text).length
    if (spanEnd > matchStart && item.start < effectiveEnd) {
      item.span.classList.add('pdf-highlight')
      if (!firstHighlighted) firstHighlighted = item.span
    }
  }

  highlightDone = true

  if (firstHighlighted) {
    requestAnimationFrame(() => {
      const container = pagesContainer.value
      if (!container || !firstHighlighted) return
      const containerRect = container.getBoundingClientRect()
      const highlightRect = firstHighlighted.getBoundingClientRect()
      const targetOffset = highlightRect.top - containerRect.top - container.clientHeight * 0.3
      container.scrollTop = Math.max(0, container.scrollTop + targetOffset)
    })
  }
}

function goToPage(pg: number, smooth = true) {
  if (pg < 1 || pg > totalPages.value) return
  currentPage.value = pg
  const el = pageRefs.get(pg)
  if (el) {
    el.scrollIntoView({ block: 'start', behavior: smooth ? 'smooth' : 'instant' })
  }
}

function goToPrevPage() {
  if (currentPage.value > 1) goToPage(currentPage.value - 1)
}

function goToNextPage() {
  if (currentPage.value < totalPages.value) goToPage(currentPage.value + 1)
}

function zoomIn() {
  if (scale.value >= 3) return
  scale.value = clampScale(Math.round((scale.value + 0.25) * 100) / 100)
  onScaleChange()
}

function zoomOut() {
  if (scale.value <= 0.5) return
  scale.value = clampScale(Math.round((scale.value - 0.25) * 100) / 100)
  onScaleChange()
}

function setZoom(nextScale: number) {
  const clamped = clampScale(nextScale)
  if (clamped === scale.value) return
  scale.value = Math.round(clamped * 100) / 100
  onScaleChange()
}

function onScaleChange() {
  // Cancel any in-flight renders so they can't complete onto a canvas that's
  // now stale. `invalidateRenders` clears scale keys and re-schedules visible
  // pages; placeholder heights update reactively via `wrapperStyle`.
  invalidateRenders()
}

function onWheel(e: WheelEvent) {
  if (e.ctrlKey || e.metaKey) {
    e.preventDefault()
    if (e.deltaY < 0) zoomIn()
    else zoomOut()
  }
}

// --- Scroll → currentPage derivation, rAF-throttled so the toolbar doesn't
//     jitter during fast scrolls. ---
let scrollRafPending = false
function updateCurrentPageFromScroll() {
  if (scrollRafPending) return
  scrollRafPending = true
  requestAnimationFrame(() => {
    scrollRafPending = false
    const container = pagesContainer.value
    if (!container) return
    const probe = container.scrollTop + container.clientHeight * 0.4
    for (const [pg, el] of pageRefs.entries()) {
      if (el.offsetTop <= probe && el.offsetTop + el.offsetHeight > probe) {
        if (pg !== currentPage.value) currentPage.value = pg
        return
      }
    }
  })
}

function onScroll() {
  updateCurrentPageFromScroll()
}

// --- Touch gesture handling ---
type Touch1 = { id: number; x: number; y: number; t: number }
let touchStart: Touch1 | null = null
let pinchInitialDistance = 0
let pinchInitialScale = 1
let pinching = false
let lastTapTime = 0

function onTouchStart(e: TouchEvent) {
  if (e.touches.length === 2) {
    pinching = true
    pinchInitialScale = scale.value
    pinchInitialDistance = pointDistance(
      { x: e.touches[0].clientX, y: e.touches[0].clientY },
      { x: e.touches[1].clientX, y: e.touches[1].clientY },
    )
    touchStart = null
  } else if (e.touches.length === 1 && !pinching) {
    const t = e.touches[0]
    touchStart = { id: t.identifier, x: t.clientX, y: t.clientY, t: performance.now() }
  }
}

function onTouchMove(e: TouchEvent) {
  if (pinching && e.touches.length === 2) {
    // Prevent the browser's native pinch (which would just blur the canvas).
    e.preventDefault()
    const d = pointDistance(
      { x: e.touches[0].clientX, y: e.touches[0].clientY },
      { x: e.touches[1].clientX, y: e.touches[1].clientY },
    )
    const next = computePinchScale(pinchInitialScale, pinchInitialDistance, d)
    // Only re-render when the scale has changed meaningfully, to avoid
    // thrashing the canvas during the pinch.
    if (Math.abs(next - scale.value) >= PINCH_RERENDER_THRESHOLD) {
      setZoom(next)
    }
  }
}

function onTouchEnd(e: TouchEvent) {
  if (pinching) {
    if (e.touches.length < 2) {
      // Commit final scale on pinch end.
      pinching = false
      pinchInitialDistance = 0
    }
    return
  }
  if (!touchStart) return
  const changed = e.changedTouches[0]
  if (!changed || changed.identifier !== touchStart.id) {
    touchStart = null
    return
  }
  const dx = changed.clientX - touchStart.x
  const dy = changed.clientY - touchStart.y
  const dt = performance.now() - touchStart.t

  // Double-tap → toggle zoom (1× ↔ 2×). Only when the gesture is a tap
  // (tiny movement) and within 300ms of the previous tap.
  const isTap =
    Math.abs(dx) < MAX_TAP_MOVEMENT_PX &&
    Math.abs(dy) < MAX_TAP_MOVEMENT_PX &&
    dt < MAX_TAP_DURATION_MS
  if (isTap) {
    const now = performance.now()
    if (now - lastTapTime < DOUBLE_TAP_WINDOW_MS) {
      setZoom(scale.value > 1 ? 1 : 2)
      lastTapTime = 0
      touchStart = null
      return
    }
    lastTapTime = now
  }

  // Horizontal swipe → page nav. Disabled when zoomed in (the user is
  // probably panning the zoomed page instead).
  if (scale.value <= 1.05) {
    const swipe = detectSwipe(dx, dy)
    if (swipe === 'left') goToNextPage()
    else if (swipe === 'right') goToPrevPage()
  }

  touchStart = null
}

onMounted(() => {
  loadPdf()
  pagesContainer.value?.addEventListener('scroll', onScroll, { passive: true })
})

onBeforeUnmount(() => {
  pagesContainer.value?.removeEventListener('scroll', onScroll)
  observer?.disconnect()
  observer = null
  resizeObserver?.disconnect()
  resizeObserver = null
  for (const task of activeRenderTasks.values()) {
    try {
      task.cancel()
    } catch {
      /* ignore */
    }
  }
  activeRenderTasks.clear()
  pdfDoc?.destroy()
  pageProxies.clear()
  renderedLru.clear()
})

// Re-setup the observer when the page list is first populated.
watch(totalPages, async (n) => {
  if (n > 0) {
    await nextTick()
    // pageRefs aren't all set until v-for flushes; setPageRef will observe
    // each on mount, so nothing more to do here.
  }
})

// Reload PDF when the source URL changes (e.g. the source preview modal
// is reused for a different citation pointing to a different PDF).
watch(
  () => props.url,
  () => {
    loadPdf()
  },
)

// Navigate to a different target page when the citation page changes
// without destroying the already-loaded document.
watch(
  () => props.page,
  async (newPage) => {
    if (!pdfDoc) return
    const clamped = Math.min(Math.max(newPage ?? 1, 1), totalPages.value)
    if (clamped === currentPage.value) return
    currentPage.value = clamped
    highlightDone = false
    await renderPage(clamped)
  },
)
</script>

<style>
/* Import the pdfjs textLayer CSS essentials inline
   since the full pdf_viewer.css is very large */
.pdf-page-viewer .textLayer {
  position: absolute;
  top: 0;
  left: 0;
  overflow: hidden;
  opacity: 1;
  line-height: 1;
  -webkit-text-size-adjust: none;
  -moz-text-size-adjust: none;
  text-size-adjust: none;
  forced-color-adjust: none;
  z-index: 2;
}

.pdf-page-viewer .textLayer :is(span, br) {
  color: transparent;
  position: absolute;
  white-space: pre;
  cursor: text;
  transform-origin: 0% 0%;
}

.pdf-page-viewer .textLayer span.markedContent {
  top: 0;
  height: 0;
}

.pdf-page-viewer .textLayer .highlight {
  margin: -1px;
  padding: 1px;
  background-color: rgb(180 0 170 / 0.25);
  border-radius: 4px;
}

.pdf-page-viewer .textLayer ::selection {
  background: rgba(0, 100, 255, 0.3);
}

/* Custom highlight for source text matching */
.pdf-page-viewer .textLayer .pdf-highlight {
  background-color: rgba(59, 130, 246, 0.35);
  border-radius: 2px;
  margin: -1px;
  padding: 1px;
}
</style>

<style scoped>
.pdf-page-viewer {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #333;
  overflow: hidden;
}

.pdf-pages-container {
  flex: 1;
  min-height: 0;
  overflow: auto;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
  /* Let the browser own vertical panning; we handle pinch + horizontal swipe. */
  touch-action: pan-y;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
  padding: 0;
}

.pdf-page-wrapper {
  position: relative;
  background: #fff;
  box-shadow: none;
  flex-shrink: 0;
  width: 100%;
}

.pdf-page-canvas {
  display: block;
  width: 100% !important;
}

.pdf-page-loading,
.pdf-page-error {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  color: #94a3b8;
  font-size: 14px;
}

/* Toolbar — Apple Liquid Glass */
.pdf-toolbar {
  position: absolute;
  left: 50%;
  bottom: 14px;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
  padding: 5px 10px;
  background: rgba(255, 255, 255, 0.18);
  border: 1px solid rgba(255, 255, 255, 0.32);
  border-radius: 50px;
  backdrop-filter: blur(28px) saturate(180%);
  -webkit-backdrop-filter: blur(28px) saturate(180%);
  box-shadow:
    0 4px 24px rgba(0, 0, 0, 0.22),
    inset 0 1px 0 rgba(255, 255, 255, 0.4);
  z-index: 5;
  white-space: nowrap;
}

.pdf-toolbar-divider {
  width: 1px;
  height: 18px;
  background: rgba(255, 255, 255, 0.3);
  margin: 0 6px;
  flex-shrink: 0;
}

.pdf-tool-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: rgba(255, 255, 255, 0.9);
  cursor: pointer;
  transition: background 0.15s;
}

.pdf-tool-btn--text {
  width: auto;
  padding: 0 10px;
  border-radius: 50px;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.01em;
}

@media (hover: hover) {
  .pdf-tool-btn:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.2);
  }
}

.pdf-tool-btn:active:not(:disabled) {
  background: rgba(255, 255, 255, 0.28);
}

.pdf-tool-btn:disabled {
  opacity: 0.3;
  cursor: default;
}

.pdf-page-info {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.9);
  min-width: 48px;
  text-align: center;
  user-select: none;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

@media (max-width: 768px) {
  .pdf-toolbar {
    bottom: calc(16px + env(safe-area-inset-bottom, 0px));
  }

  .pdf-page-info {
    min-width: 44px;
  }
}
</style>
