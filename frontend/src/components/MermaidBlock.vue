<template>
  <div class="mermaid-block" @mouseenter="hovered = true" @mouseleave="hovered = false">
    <div class="mermaid-toolbar" :class="{ visible: hovered }">
      <button v-if="mode === 'diagram'" class="mermaid-tool-btn" @click="mode = 'text'">
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
          <polyline points="4 7 4 4 20 4 20 7" />
          <line x1="9" y1="20" x2="15" y2="20" />
          <line x1="12" y1="4" x2="12" y2="20" />
        </svg>
        Switch to text
      </button>
      <button v-else class="mermaid-tool-btn" @click="switchToDiagram">
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
          <rect x="3" y="3" width="7" height="7" />
          <rect x="14" y="3" width="7" height="7" />
          <rect x="14" y="14" width="7" height="7" />
          <rect x="3" y="14" width="7" height="7" />
        </svg>
        Switch to diagram
      </button>
      <button
        v-if="mode === 'diagram' && ready && !renderError"
        class="mermaid-tool-btn"
        title="Download SVG"
        @click="downloadSvg"
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
        Download
      </button>
    </div>
    <div
      ref="diagramViewportEl"
      v-show="mode === 'diagram' && ready && !renderError"
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
      <div class="mermaid-controls">
        <button class="mermaid-ctrl-btn" aria-label="Fullscreen" title="Fullscreen" @click="toggleFullscreen">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path
              d="M1.75 10a.75.75 0 0 1 .75.75v2.5c0 .138.112.25.25.25h2.5a.75.75 0 0 1 0 1.5h-2.5A1.75 1.75 0 0 1 1 13.25v-2.5a.75.75 0 0 1 .75-.75Zm12.5 0a.75.75 0 0 1 .75.75v2.5A1.75 1.75 0 0 1 13.25 15h-2.5a.75.75 0 0 1 0-1.5h2.5a.25.25 0 0 0 .25-.25v-2.5a.75.75 0 0 1 .75-.75ZM2.75 2.5a.25.25 0 0 0-.25.25v2.5a.75.75 0 0 1-1.5 0v-2.5C1 1.784 1.784 1 2.75 1h2.5a.75.75 0 0 1 0 1.5ZM10 1.75a.75.75 0 0 1 .75-.75h2.5c.966 0 1.75.784 1.75 1.75v2.5a.75.75 0 0 1-1.5 0v-2.5a.25.25 0 0 0-.25-.25h-2.5a.75.75 0 0 1-.75-.75Z"
            />
          </svg>
        </button>
        <button
          class="mermaid-ctrl-btn"
          aria-label="Zoom out"
          title="Zoom out"
          :disabled="!canZoomOut"
          @click="zoomOut"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path d="M2 7.75A.75.75 0 0 1 2.75 7h10a.75.75 0 0 1 0 1.5h-10A.75.75 0 0 1 2 7.75Z" />
          </svg>
        </button>
        <button
          class="mermaid-ctrl-btn"
          aria-label="Zoom in"
          title="Zoom in"
          :disabled="!canZoomIn"
          @click="zoomIn"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path d="M7.75 2a.75.75 0 0 1 .75.75V7h4.25a.75.75 0 0 1 0 1.5H8.5v4.25a.75.75 0 0 1-1.5 0V8.5H2.75a.75.75 0 0 1 0-1.5H7V2.75A.75.75 0 0 1 7.75 2Z" />
          </svg>
        </button>
      </div>
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

</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import type mermaidType from 'mermaid'
import { sanitizeMermaidCode } from '../utils/mermaidSanitize'

const props = defineProps<{ code: string; initialZoom?: 'fit' | 'max' }>()

const mode = ref<'diagram' | 'text'>('diagram')
const hovered = ref(false)
const ready = ref(false)
const renderedSvg = ref('')
const renderError = ref<string | null>(null)
const diagramEl = ref<HTMLElement | null>(null)
const diagramViewportEl = ref<HTMLElement | null>(null)
let renderCounter = 0

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

const ZOOM_STEP = 0.2
const MIN_SCALE = 0.2
const MAX_SCALE = 5

/**
 * Scale the rendered SVG so its natural width fills the container on first render.
 * Reads dimensions from the SVG viewBox/width attribute and the always-visible
 * outer .mermaid-block element (which is never hidden by v-show).
 */
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

  const svgNaturalHeight = vb && vb.height > 0 ? vb.height : parseFloat(svg.getAttribute('height') ?? '0')
  const viewportHeight = block ? Math.max(block.clientHeight - 32, 0) : 0

  if (props.initialZoom === 'max') {
    // Start at max scale but anchored to top-left so the diagram is always
    // visible — the user can pan to explore the rest.
    scale.value = MAX_SCALE
    panX.value = 0
    panY.value = 0
  } else {
    scale.value = Math.min(Math.max(containerWidth / svgNaturalWidth, MIN_SCALE), MAX_SCALE)
    const scaledWidth = svgNaturalWidth * scale.value
    const scaledHeight = svgNaturalHeight > 0 ? svgNaturalHeight * scale.value : 0
    panX.value = Math.max((containerWidth - scaledWidth) / 2, 0)
    panY.value = Math.max((viewportHeight - scaledHeight) / 2, 0)
  }
}

function zoomIn() {
  scale.value = Math.min(MAX_SCALE, +(scale.value + ZOOM_STEP).toFixed(2))
}
function zoomOut() {
  scale.value = Math.max(MIN_SCALE, +(scale.value - ZOOM_STEP).toFixed(2))
}
function syncFullscreenState() {
  const active = document.fullscreenElement
  const host = diagramViewportEl.value
  if (!host || active !== host) {
    isDragging.value = false
    activePointerId = null
  }
}

async function toggleFullscreen() {
  const host = diagramViewportEl.value
  if (!host) return

  if (document.fullscreenElement === host) {
    await document.exitFullscreen()
    return
  }

  await host.requestFullscreen()
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
  const deltaX = event.clientX - dragStartX
  const deltaY = event.clientY - dragStartY
  panX.value = dragStartPanX + deltaX
  panY.value = dragStartPanY + deltaY
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
    // theme: 'base',
    // themeVariables: {
    //   darkMode: false,
    //   background: '#f4f4f4',
    //   primaryColor: '#ede9fe',
    //   primaryTextColor: '#000000',
    //   primaryBorderColor: '#7c3aed',
    //   secondaryColor: '#e2e8f0',
    //   secondaryTextColor: '#000000',
    //   tertiaryColor: '#f1f5f9',
    //   tertiaryTextColor: '#000000',
    //   lineColor: '#475569',
    //   textColor: '#000000',
    //   nodeTextColor: '#000000',
    //   labelTextColor: '#000000',
    // },
    flowchart: { htmlLabels: true, curve: 'basis' },
    securityLevel: 'loose',
  })
  return mermaid
}

/**
 * Renders the mermaid source into an SVG and mounts it into the diagram
 * container. On failure we surface an error but stay in diagram mode so the
 * user can retry once the source updates (e.g. during streaming) or by
 * toggling the diagram view.
 */
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
    // Auto-zoom to fit width before revealing. If the container has no layout
    // yet (e.g. modal still rendering), retry after the next paint.
    fitToWidth()
    requestAnimationFrame(() => {
      const block = diagramEl.value?.closest('.mermaid-block') as HTMLElement | null
      if (block && block.clientWidth <= 0) {
        // Container still has no size — retry once more after browser layout
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
    // Stay in diagram mode and surface the error so failing renders don't
    // silently flip the view to text and trap the user there.
    console.error('[MermaidBlock] Failed to render diagram', err)
    renderError.value = err instanceof Error ? err.message : String(err)
    renderedSvg.value = ''
    if (diagramEl.value) diagramEl.value.innerHTML = ''
    ready.value = true
  }
}

function switchToDiagram() {
  mode.value = 'diagram'
  // Re-render if we don't yet have a successful render (previous attempt
  // failed, component mounted while hidden, etc.).
  if (!renderedSvg.value) {
    nextTick(renderDiagram)
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
  document.addEventListener('fullscreenchange', syncFullscreenState)
})

onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', syncFullscreenState)
})

watch(
  () => props.code,
  () => {
    nextTick(renderDiagram)
  },
)
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

.mermaid-toolbar {
  position: absolute;
  top: 8px;
  right: 8px;
  display: flex;
  gap: 4px;
  z-index: 2;
  opacity: 0;
  transition: opacity 0.15s;
}

.mermaid-toolbar.visible {
  opacity: 1;
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

.mermaid-controls {
  position: absolute;
  bottom: 10px;
  right: 10px;
  display: flex;
  gap: 6px;
  background: rgba(15, 20, 35, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 6px;
  padding: 4px;
  backdrop-filter: blur(4px);
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

.mermaid-diagram:fullscreen {
  background: #0f172a;
  padding: 24px;
}
</style>
