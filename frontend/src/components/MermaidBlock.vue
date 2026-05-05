<template>
  <div class="mermaid-block">
    <!-- Controls bar: zoom group left, actions right -->
    <div v-if="mode === 'diagram' && ready && !renderError" class="mermaid-controls-bar">
      <div class="mermaid-zoom-group">
        <button class="mermaid-ctrl-btn" aria-label="Zoom out" title="Zoom out" :disabled="!canZoomOut" @click="zoomOut">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path d="M2 7.75A.75.75 0 0 1 2.75 7h10a.75.75 0 0 1 0 1.5h-10A.75.75 0 0 1 2 7.75Z" />
          </svg>
        </button>
        <span class="mermaid-zoom-label">{{ Math.round(scale * 100) }}%</span>
        <button class="mermaid-ctrl-btn" aria-label="Zoom in" title="Zoom in" :disabled="!canZoomIn" @click="zoomIn">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path d="M7.75 2a.75.75 0 0 1 .75.75V7h4.25a.75.75 0 0 1 0 1.5H8.5v4.25a.75.75 0 0 1-1.5 0V8.5H2.75a.75.75 0 0 1 0-1.5H7V2.75A.75.75 0 0 1 7.75 2Z" />
          </svg>
        </button>
      </div>
      <div class="mermaid-action-group">
        <button class="mermaid-tool-btn" @click="mode = 'text'">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="4 7 4 4 20 4 20 7" /><line x1="9" y1="20" x2="15" y2="20" /><line x1="12" y1="4" x2="12" y2="20" />
          </svg>
          Switch to text
        </button>
        <button class="mermaid-tool-btn" @click="downloadSvg">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" />
          </svg>
          Download
        </button>
        <button class="mermaid-tool-btn" aria-label="Fullscreen diagram" title="Fullscreen" @click="openPopup">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 3 21 3 21 9" /><polyline points="9 21 3 21 3 15" /><line x1="21" y1="3" x2="14" y2="10" /><line x1="3" y1="21" x2="10" y2="14" />
          </svg>
          Fullscreen
        </button>
      </div>
    </div>
    <div v-else-if="mode === 'text'" class="mermaid-controls-bar mermaid-controls-bar--text">
      <button class="mermaid-tool-btn" @click="switchToDiagram">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" />
          <rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" />
        </svg>
        Switch to diagram
      </button>
    </div>
    <div
      v-show="mode === 'diagram' && ready && !renderError"
      ref="diagramViewportEl"
      class="mermaid-diagram"
      :class="{ 'is-dragging': isDragging }"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
    >
      <div
        ref="diagramEl"
        class="mermaid-svg-wrapper"
        :class="{ 'is-dragging': isDragging }"
        :style="{ transform: svgTransform }"
      ></div>
    </div>
    <div v-if="mode === 'diagram' && !ready" class="mermaid-loading">
      <span class="mermaid-loading-dot"></span>
      <span class="mermaid-loading-dot"></span>
      <span class="mermaid-loading-dot"></span>
    </div>
    <div v-if="mode === 'diagram' && ready && renderError" class="mermaid-error">
      <p class="mermaid-error-title">Could not render diagram</p>
      <p class="mermaid-error-message">{{ renderError }}</p>
      <pre class="mermaid-source"><code>{{ code }}</code></pre>
    </div>
    <pre v-show="mode === 'text'" class="mermaid-source"><code>{{ code }}</code></pre>
  </div>

  <!-- Popup overlay -->
  <Teleport to="body">
    <div
      v-if="popupOpen"
      class="mermaid-popup-overlay"
      @click.self="popupOpen = false"
      @keydown.esc.capture="popupOpen = false"
    >
      <div class="mermaid-popup-dialog">
        <div class="mermaid-popup-header">
          <div class="mermaid-popup-controls">
            <button class="mermaid-popup-ctrl-btn" aria-label="Zoom out" title="Zoom out" :disabled="popupScale <= POPUP_MIN_SCALE" @click="popupZoomOut">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M2 7.75A.75.75 0 0 1 2.75 7h10a.75.75 0 0 1 0 1.5h-10A.75.75 0 0 1 2 7.75Z" /></svg>
            </button>
            <span class="mermaid-popup-zoom-label">{{ Math.round(popupScale * 100) }}%</span>
            <button class="mermaid-popup-ctrl-btn" aria-label="Zoom in" title="Zoom in" :disabled="popupScale >= POPUP_MAX_SCALE" @click="popupZoomIn">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M7.75 2a.75.75 0 0 1 .75.75V7h4.25a.75.75 0 0 1 0 1.5H8.5v4.25a.75.75 0 0 1-1.5 0V8.5H2.75a.75.75 0 0 1 0-1.5H7V2.75A.75.75 0 0 1 7.75 2Z" /></svg>
            </button>
          </div>
          <button class="mermaid-popup-close" aria-label="Close" @click="popupOpen = false">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div
          ref="popupViewportEl"
          class="mermaid-popup-viewport"
          :class="{ 'is-dragging': popupIsDragging }"
          @pointerdown="onPopupPointerDown"
          @pointermove="onPopupPointerMove"
          @pointerup="onPopupPointerUp"
          @pointercancel="onPopupPointerCancel"
          @dblclick="onPopupDblClick"
        >
          <!-- eslint-disable vue/no-v-html -- renderedSvg is sanitized Mermaid output, no user content -->
          <div
            class="mermaid-popup-svg-inner"
            :style="{ transform: `translate(${popupPanX}px, ${popupPanY}px) scale(${popupScale})`, transformOrigin: 'top left' }"
            v-html="renderedSvg"
          />
          <!-- eslint-enable vue/no-v-html -->
        </div>
      </div>
    </div>
  </Teleport>

</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import type mermaidType from 'mermaid'
import { sanitizeMermaidCode } from '../utils/mermaidSanitize'

const props = defineProps<{ code: string; initialZoom?: 'fit' | 'max' | number }>()

const mode = ref<'diagram' | 'text'>('diagram')
const ready = ref(false)
const renderedSvg = ref('')
const renderError = ref<string | null>(null)
const diagramEl = ref<HTMLElement | null>(null)
const diagramViewportEl = ref<HTMLElement | null>(null)
let renderCounter = 0

// ── Inline pan / zoom ────────────────────────────────────────────────────────
const scale = ref(1)
const panX = ref(0)
const panY = ref(0)
const isDragging = ref(false)

let activePointerId: number | null = null
let dragStartX = 0
let dragStartY = 0
let dragStartPanX = 0
let dragStartPanY = 0

const svgTransform = computed(
  () => `translate(${panX.value}px, ${panY.value}px) scale(${scale.value})`,
)

const canZoomIn = computed(() => scale.value < MAX_SCALE)
const canZoomOut = computed(() => scale.value > MIN_SCALE)

const ZOOM_STEP = 1.0
const MIN_SCALE = 0.2
const MAX_SCALE = 7

// ── Popup state ─────────────────────────────────────────────────────────────
const popupOpen = ref(false)
const popupScale = ref(1)
const popupPanX = ref(0)
const popupPanY = ref(0)
const popupIsDragging = ref(false)
const popupViewportEl = ref<HTMLElement | null>(null)

let popupActivePointerId: number | null = null
let popupDragStartX = 0
let popupDragStartY = 0
let popupDragStartPanX = 0
let popupDragStartPanY = 0

let popupLastTapTime = 0
let popupLastTapX = 0
let popupLastTapY = 0

const POPUP_MIN_SCALE = 0.2
const POPUP_MAX_SCALE = 8
const POPUP_ZOOM_STEP = 1.0
const POPUP_INITIAL_SCALE = 4

function popupZoomIn() {
  popupScale.value = Math.min(POPUP_MAX_SCALE, +(popupScale.value + POPUP_ZOOM_STEP).toFixed(2))
}
function popupZoomOut() {
  popupScale.value = Math.max(POPUP_MIN_SCALE, +(popupScale.value - POPUP_ZOOM_STEP).toFixed(2))
}

function openPopup() {
  if (!renderedSvg.value) return
  popupScale.value = Math.min(Math.max(POPUP_INITIAL_SCALE, POPUP_MIN_SCALE), POPUP_MAX_SCALE)
  popupPanX.value = 0
  popupPanY.value = 0
  popupOpen.value = true
}

function zoomPopupAt(clientX: number, clientY: number, delta: number) {
  const oldScale = popupScale.value
  const newScale = Math.min(POPUP_MAX_SCALE, Math.max(POPUP_MIN_SCALE, +(oldScale + delta).toFixed(2)))
  if (newScale === oldScale) return
  const rect = popupViewportEl.value?.getBoundingClientRect() ?? { left: 0, top: 0 }
  const lx = clientX - rect.left
  const ly = clientY - rect.top
  const ratio = newScale / oldScale
  popupPanX.value = lx - (lx - popupPanX.value) * ratio
  popupPanY.value = ly - (ly - popupPanY.value) * ratio
  popupScale.value = newScale
}

type DragPointerEvent = {
  pointerId: number
  pointerType?: string
  button?: number
  clientX: number
  clientY: number
  target: unknown
  currentTarget: unknown
  preventDefault: () => void
}

function onPopupPointerDown(event: DragPointerEvent) {
  if (event.pointerType !== 'touch' && event.button !== 0) return
  const target = event.target
  if (target instanceof HTMLElement && target.closest('.mermaid-popup-header')) return

  popupActivePointerId = event.pointerId
  popupDragStartX = event.clientX
  popupDragStartY = event.clientY
  popupDragStartPanX = popupPanX.value
  popupDragStartPanY = popupPanY.value
  popupIsDragging.value = true

  const currentTarget = event.currentTarget
  if (currentTarget instanceof HTMLElement) currentTarget.setPointerCapture(event.pointerId)
  event.preventDefault()
}

function onPopupPointerMove(event: DragPointerEvent) {
  if (!popupIsDragging.value || event.pointerId !== popupActivePointerId) return
  popupPanX.value = popupDragStartPanX + (event.clientX - popupDragStartX)
  popupPanY.value = popupDragStartPanY + (event.clientY - popupDragStartY)
  event.preventDefault()
}

function onPopupPointerUp(event: DragPointerEvent) {
  if (event.pointerId !== popupActivePointerId) return
  const currentTarget = event.currentTarget
  if (currentTarget instanceof HTMLElement) currentTarget.releasePointerCapture(event.pointerId)

  const wasTap =
    Math.abs(event.clientX - popupDragStartX) < 5 &&
    Math.abs(event.clientY - popupDragStartY) < 5

  popupIsDragging.value = false
  popupActivePointerId = null

  if (wasTap) {
    const now = Date.now()
    const dx = event.clientX - popupLastTapX
    const dy = event.clientY - popupLastTapY
    const isDoubleTap = now - popupLastTapTime < 300 && dx * dx + dy * dy < 40 * 40
    if (isDoubleTap) {
      zoomPopupAt(event.clientX, event.clientY, POPUP_ZOOM_STEP)
      popupLastTapTime = 0
    } else {
      popupLastTapTime = now
      popupLastTapX = event.clientX
      popupLastTapY = event.clientY
    }
  }
}

function onPopupPointerCancel(event: Pick<DragPointerEvent, 'pointerId' | 'currentTarget'>) {
  if (event.pointerId !== popupActivePointerId) return
  const currentTarget = event.currentTarget
  if (currentTarget instanceof HTMLElement) currentTarget.releasePointerCapture(event.pointerId)
  popupIsDragging.value = false
  popupActivePointerId = null
}

function onPopupDblClick(event: MouseEvent) {
  // dblclick fires for mouse; touch double-tap is handled via pointer events above
  zoomPopupAt(event.clientX, event.clientY, POPUP_ZOOM_STEP)
}

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape' && popupOpen.value) popupOpen.value = false
}

// ── Inline pan / drag handlers ───────────────────────────────────────────────

function fitToWidth() {
  if (!diagramEl.value) return
  const svg = diagramEl.value.querySelector('svg')
  if (!svg) return

  const block = diagramEl.value.closest('.mermaid-block') as HTMLElement | null
  const containerWidth = block ? block.clientWidth : 0
  if (containerWidth <= 0) return

  const vb = svg.viewBox?.baseVal
  const svgNaturalWidth =
    vb && vb.width > 0 ? vb.width : parseFloat(svg.getAttribute('width') ?? '0')
  if (svgNaturalWidth <= 0) return

  if (typeof props.initialZoom === 'number') {
    scale.value = Math.min(Math.max(props.initialZoom, MIN_SCALE), MAX_SCALE)
    panX.value = 0
    panY.value = 0
  } else if (props.initialZoom === 'max') {
    scale.value = MAX_SCALE
    panX.value = 0
    panY.value = 0
  } else {
    scale.value = MAX_SCALE
    panX.value = 0
    panY.value = 0
  }
}

function zoomIn() {
  scale.value = Math.min(MAX_SCALE, +(scale.value + ZOOM_STEP).toFixed(2))
}
function zoomOut() {
  scale.value = Math.max(MIN_SCALE, +(scale.value - ZOOM_STEP).toFixed(2))
}

function onPointerDown(event: DragPointerEvent) {
  if (mode.value !== 'diagram' || !ready.value) return
  if (event.pointerType !== 'touch' && event.button !== 0) return

  const target = event.target
  if (
    target instanceof HTMLElement &&
    target.closest('.mermaid-controls, .mermaid-toolbar, .mermaid-ctrl-btn, .mermaid-tool-btn')
  ) {
    return
  }

  activePointerId = event.pointerId
  dragStartX = event.clientX
  dragStartY = event.clientY
  dragStartPanX = panX.value
  dragStartPanY = panY.value
  isDragging.value = true

  const currentTarget = event.currentTarget
  if (currentTarget instanceof HTMLElement) {
    currentTarget.setPointerCapture(event.pointerId)
  }
  event.preventDefault()
}

function onPointerMove(event: DragPointerEvent) {
  if (!isDragging.value || event.pointerId !== activePointerId) return
  const dx = event.clientX - dragStartX
  const dy = event.clientY - dragStartY
  panX.value = dragStartPanX + dx
  panY.value = dragStartPanY + dy
  event.preventDefault()
}

function onPointerUp(event: Pick<DragPointerEvent, 'pointerId' | 'currentTarget'>) {
  if (event.pointerId !== activePointerId) return

  const currentTarget = event.currentTarget
  if (currentTarget instanceof HTMLElement) {
    currentTarget.releasePointerCapture(event.pointerId)
  }

  isDragging.value = false
  activePointerId = null
}

let mermaid: typeof mermaidType | null = null

async function getMermaid() {
  if (mermaid) return mermaid
  const mod = await import('mermaid')
  mermaid = mod.default
  mermaid.initialize({
    startOnLoad: false,
    look: 'handDrawn',
    theme: 'forest',
    flowchart: { htmlLabels: true, curve: 'basis' },
    securityLevel: 'loose',
    suppressErrorRendering: true,
  })
  return mermaid
}

async function renderDiagram() {
  if (!diagramEl.value) return
  if (props.code.trim().length === 0) {
    ready.value = false
    renderError.value = null
    return
  }
  ready.value = false
  renderError.value = null
  try {
    const m = await getMermaid()
    const id = `mermaid-${Date.now()}-${renderCounter++}`
    const { svg } = await m.render(id, sanitizeMermaidCode(props.code))
    diagramEl.value.innerHTML = svg
    renderedSvg.value = svg
    fitToWidth()
    requestAnimationFrame(() => {
      const block = diagramEl.value?.closest('.mermaid-block') as HTMLElement | null
      if (block && block.clientWidth <= 0) {
        requestAnimationFrame(() => {
          fitToWidth()
          ready.value = true
        })
      } else {
        if (block && block.clientWidth > 0) fitToWidth()
        ready.value = true
      }
    })
  } catch (err) {
    console.error('[MermaidBlock] Failed to render diagram', err)
    renderError.value = err instanceof Error ? err.message : String(err)
    renderedSvg.value = ''
    if (diagramEl.value) diagramEl.value.innerHTML = ''
    ready.value = true
  }
}

function switchToDiagram() {
  mode.value = 'diagram'
  // When returning to diagram mode after a failed render (renderError set) or
  // when there's no SVG yet, trigger a fresh render immediately.
  // We can't rely solely on the mode-watcher because Vue de-duplicates watcher
  // jobs – if mode was already 'diagram' before switching to 'text', the
  // watcher sees no net change and won't fire.
  if (renderError.value || !renderedSvg.value) {
    renderDiagram()
  }
}

function downloadSvg() {
  const svgContent = renderedSvg.value
  if (!svgContent) return
  const blob = new Blob([svgContent], { type: 'image/svg+xml;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'diagram.svg'
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(() => {
  renderDiagram()
  document.addEventListener('keydown', onKeyDown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeyDown)
})

// Re-render when switching to diagram mode (diagram el must be in DOM first).
// Guard against double-render with switchToDiagram: if renderDiagram was
// already called (ready becomes false), skip the watch-triggered render.
watch(mode, (m) => {
  if (m === 'diagram' && !renderedSvg.value && ready.value) renderDiagram()
}, { flush: 'post' })

// Re-render when the code prop changes, after Vue has updated the DOM.
watch(() => props.code, renderDiagram, { flush: 'post' })
</script>

<style scoped>
.mermaid-block {
  position: relative;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  margin: 8px 0;
  overflow: hidden;
}

.mermaid-controls-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.02);
  flex-shrink: 0;
}

.mermaid-controls-bar--text {
  justify-content: flex-end;
}

.mermaid-zoom-group {
  display: flex;
  align-items: center;
  gap: 4px;
}

.mermaid-zoom-label {
  font-size: 11px;
  color: rgba(148, 163, 184, 0.7);
  min-width: 38px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.mermaid-action-group {
  display: flex;
  align-items: center;
  gap: 4px;
}

.mermaid-tool-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: rgba(30, 41, 59, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #94a3b8;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 11px;
  cursor: pointer;
  transition:
    background 0.15s,
    color 0.15s,
    border-color 0.15s;
  font-family: inherit;
  white-space: nowrap;
}

@media (hover: hover) {
  .mermaid-tool-btn:hover {
    background: rgba(167, 139, 250, 0.12);
    border-color: rgba(167, 139, 250, 0.3);
    color: #c4b5fd;
  }
}
.mermaid-tool-btn:active {
  background: rgba(167, 139, 250, 0.12);
  border-color: rgba(167, 139, 250, 0.3);
  color: #c4b5fd;
}

.mermaid-diagram {
  position: relative;
  padding: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  min-height: 500px;
  cursor: grab;
  touch-action: none;
}

.mermaid-diagram.is-dragging {
  cursor: grabbing;
}

.mermaid-svg-wrapper {
  transform-origin: center center;
  transition: transform 0.18s cubic-bezier(0.22, 0.61, 0.36, 1);
  will-change: transform;
}

.mermaid-svg-wrapper.is-dragging {
  transition: none;
}

.mermaid-svg-wrapper :deep(svg) {
  max-width: 100%;
  height: auto;
}

.mermaid-svg-wrapper :deep(svg foreignObject),
.mermaid-svg-wrapper :deep(svg foreignObject *),
.mermaid-svg-wrapper :deep(svg .nodeLabel),
.mermaid-svg-wrapper :deep(svg .edgeLabel),
.mermaid-svg-wrapper :deep(svg text) {
  color: #000 !important;
  fill: #000 !important;
}

.mermaid-ctrl-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  background: transparent;
  border: none;
  color: #64748b;
  border-radius: 4px;
  cursor: pointer;
  transition:
    background 0.12s,
    color 0.12s;
  padding: 0;
}

.mermaid-ctrl-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

@media (hover: hover) {
  .mermaid-ctrl-btn:hover {
    background: rgba(255, 255, 255, 0.07);
    color: #c4b5fd;
  }
}
.mermaid-ctrl-btn:active {
  background: rgba(167, 139, 250, 0.15);
  color: #c4b5fd;
}
.mermaid-source {
  background: none;
  border: none;
  margin: 0;
  padding: 12px;
  overflow-x: auto;
}

.mermaid-source code {
  background: none;
  padding: 0;
  font-size: 13px;
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
  color: #e2e8f0;
}

.mermaid-error {
  padding: 12px 16px;
  color: #fca5a5;
}

.mermaid-error-title {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 600;
}

.mermaid-error-message {
  margin: 0 0 8px;
  font-size: 12px;
  color: #f87171;
  white-space: pre-wrap;
  word-break: break-word;
}

.mermaid-loading {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 6px;
  padding: 32px 16px;
}

.mermaid-loading-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #64748b;
  animation: mermaid-pulse 1s ease-in-out infinite;
}

.mermaid-loading-dot:nth-child(2) {
  animation-delay: 0.15s;
}
.mermaid-loading-dot:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes mermaid-pulse {
  0%,
  100% {
    opacity: 0.3;
    transform: scale(0.8);
  }
  50% {
    opacity: 1;
    transform: scale(1);
  }
}

/* ── Popup overlay ────────────────────────────────────────────────────────── */

.mermaid-popup-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.78);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  box-sizing: border-box;
  cursor: default;
}

.mermaid-popup-dialog {
  background: rgba(10, 13, 22, 0.96);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: none;
  border-radius: 0;
  width: 100vw;
  height: 100vh;
  max-width: none;
  max-height: none;
  display: flex;
  flex-direction: column;
  box-shadow: none;
  cursor: default;
  overflow: hidden;
}

.mermaid-popup-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px 8px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.07);
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.02);
}

.mermaid-popup-controls {
  display: flex;
  align-items: center;
  gap: 4px;
}

.mermaid-popup-zoom-label {
  font-size: 11px;
  color: rgba(148, 163, 184, 0.7);
  min-width: 38px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.mermaid-popup-ctrl-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.04);
  color: rgba(148, 163, 184, 0.8);
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}

.mermaid-popup-ctrl-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

@media (hover: hover) {
  .mermaid-popup-ctrl-btn:not(:disabled):hover {
    background: rgba(167, 139, 250, 0.15);
    color: #c4b5fd;
  }
}

.mermaid-popup-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.6);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  margin-left: 8px;
  flex-shrink: 0;
}

@media (hover: hover) {
  .mermaid-popup-close:hover {
    background: rgba(255, 255, 255, 0.1);
    color: rgba(255, 255, 255, 0.9);
  }
}

.mermaid-popup-viewport {
  flex: 1;
  overflow: hidden;
  position: relative;
  cursor: grab;
  touch-action: none;
  min-height: 300px;
  background: #fff;
}

.mermaid-popup-viewport.is-dragging {
  cursor: grabbing;
}

.mermaid-popup-svg-inner {
  position: absolute;
  top: 16px;
  left: 16px;
  transform-origin: top left;
  transition: transform 0.15s ease;
}

.mermaid-popup-svg-inner.is-dragging {
  transition: none;
}

.mermaid-popup-svg-inner :deep(svg) {
  display: block;
  max-width: none;
}

.mermaid-popup-svg-inner :deep(svg foreignObject),
.mermaid-popup-svg-inner :deep(svg foreignObject *),
.mermaid-popup-svg-inner :deep(svg .nodeLabel),
.mermaid-popup-svg-inner :deep(svg .edgeLabel),
.mermaid-popup-svg-inner :deep(svg text) {
  color: #000 !important;
  fill: #000 !important;
}
</style>
