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
      <button v-if="mode === 'diagram' && ready && !renderError" class="mermaid-tool-btn" title="Download SVG" @click="downloadSvg">
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
      <button v-if="mode === 'diagram' && ready && !renderError" class="mermaid-tool-btn" title="Fullscreen" @click="fullscreen = true">
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
          <polyline points="15 3 21 3 21 9" />
          <polyline points="9 21 3 21 3 15" />
          <line x1="21" y1="3" x2="14" y2="10" />
          <line x1="3" y1="21" x2="10" y2="14" />
        </svg>
        Fullscreen
      </button>
    </div>
    <div
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
        <button class="mermaid-ctrl-btn" aria-label="Zoom in" title="Zoom in" @click="zoomIn">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path d="M3.75 7.5a.75.75 0 0 1 .75-.75h2.25V4.5a.75.75 0 0 1 1.5 0v2.25h2.25a.75.75 0 0 1 0 1.5H8.25v2.25a.75.75 0 0 1-1.5 0V8.25H4.5a.75.75 0 0 1-.75-.75Z"/>
            <path d="M7.5 0a7.5 7.5 0 0 1 5.807 12.247l2.473 2.473a.749.749 0 1 1-1.06 1.06l-2.473-2.473A7.5 7.5 0 1 1 7.5 0Zm-6 7.5a6 6 0 1 0 12 0 6 6 0 0 0-12 0Z"/>
          </svg>
        </button>
        <button class="mermaid-ctrl-btn" aria-label="Zoom out" title="Zoom out" @click="zoomOut">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path d="M4.5 6.75h6a.75.75 0 0 1 0 1.5h-6a.75.75 0 0 1 0-1.5Z"/>
            <path d="M0 7.5a7.5 7.5 0 1 1 13.307 4.747l2.473 2.473a.749.749 0 1 1-1.06 1.06l-2.473-2.473A7.5 7.5 0 0 1 0 7.5Zm7.5-6a6 6 0 1 0 0 12 6 6 0 0 0 0-12Z"/>
          </svg>
        </button>
        <button class="mermaid-ctrl-btn" aria-label="Pan up" title="Pan up" @click="panUp">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path d="M3.22 10.53a.749.749 0 0 1 0-1.06l4.25-4.25a.749.749 0 0 1 1.06 0l4.25 4.25a.749.749 0 1 1-1.06 1.06L8 6.811 4.28 10.53a.749.749 0 0 1-1.06 0Z"/>
          </svg>
        </button>
        <button class="mermaid-ctrl-btn" aria-label="Pan down" title="Pan down" @click="panDown">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path d="M12.78 5.22a.749.749 0 0 1 0 1.06l-4.25 4.25a.749.749 0 0 1-1.06 0L3.22 6.28a.749.749 0 1 1 1.06-1.06L8 8.939l3.72-3.719a.749.749 0 0 1 1.06 0Z"/>
          </svg>
        </button>
        <button class="mermaid-ctrl-btn" aria-label="Pan left" title="Pan left" @click="panLeft">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path d="M9.78 12.78a.75.75 0 0 1-1.06 0L4.47 8.53a.75.75 0 0 1 0-1.06l4.25-4.25a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042L6.06 8l3.72 3.72a.75.75 0 0 1 0 1.06Z"/>
          </svg>
        </button>
        <button class="mermaid-ctrl-btn" aria-label="Pan right" title="Pan right" @click="panRight">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path d="M6.22 3.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042L9.94 8 6.22 4.28a.75.75 0 0 1 0-1.06Z"/>
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

  <!-- Fullscreen overlay -->
  <Teleport to="body">
    <div v-if="fullscreen" class="mermaid-fullscreen-overlay" @click.self="fullscreen = false" @keydown.esc="fullscreen = false">
      <div class="mermaid-fullscreen-inner">
        <button class="mermaid-fullscreen-close" title="Close" @click="fullscreen = false">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
        <!-- eslint-disable-next-line vue/no-v-html -->
        <div class="mermaid-fullscreen-diagram" v-html="renderedSvg"></div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import type mermaidType from 'mermaid'

const props = defineProps<{ code: string }>()

const mode = ref<'diagram' | 'text'>('diagram')
const hovered = ref(false)
const ready = ref(false)
const fullscreen = ref(false)
const renderedSvg = ref('')
const renderError = ref<string | null>(null)
const diagramEl = ref<HTMLElement | null>(null)
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

const ZOOM_STEP = 0.2
const PAN_STEP = 40
const MIN_SCALE = 0.2
const MAX_SCALE = 5

function zoomIn() {
  scale.value = Math.min(MAX_SCALE, +(scale.value + ZOOM_STEP).toFixed(2))
}
function zoomOut() {
  scale.value = Math.max(MIN_SCALE, +(scale.value - ZOOM_STEP).toFixed(2))
}
function panUp() { panY.value -= PAN_STEP }
function panDown() { panY.value += PAN_STEP }
function panLeft() { panX.value -= PAN_STEP }
function panRight() { panX.value += PAN_STEP }

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
    target instanceof HTMLElement
    && target.closest('.mermaid-controls, .mermaid-toolbar, .mermaid-ctrl-btn, .mermaid-tool-btn')
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
    theme: 'base',
    themeVariables: {
      darkMode: false,
      background: '#f4f4f4',
      primaryColor: '#ede9fe',
      primaryTextColor: '#000000',
      primaryBorderColor: '#7c3aed',
      secondaryColor: '#e2e8f0',
      secondaryTextColor: '#000000',
      tertiaryColor: '#f1f5f9',
      tertiaryTextColor: '#000000',
      lineColor: '#475569',
      textColor: '#000000',
      nodeTextColor: '#000000',
      labelTextColor: '#000000',
    },
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
    const { svg } = await m.render(id, props.code)
    diagramEl.value.innerHTML = svg
    renderedSvg.value = svg
    // Wait one frame so the browser paints the SVG before revealing
    requestAnimationFrame(() => {
      ready.value = true
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
  justify-content: center;
  overflow: hidden;
  min-height: 80px;
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
  gap: 2px;
  background: rgba(15, 20, 35, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 6px;
  padding: 3px;
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
  transition: background 0.12s, color 0.12s;
  padding: 0;
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

.mermaid-fullscreen-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.75);
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(4px);
}

.mermaid-fullscreen-inner {
  position: relative;
  background: #1e1e2e;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  max-width: 90vw;
  max-height: 90vh;
  overflow: auto;
  padding: 48px 24px 24px;
}

.mermaid-fullscreen-close {
  position: absolute;
  top: 12px;
  right: 12px;
  background: rgba(30, 41, 59, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #94a3b8;
  border-radius: 6px;
  padding: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, color 0.15s;
}

.mermaid-fullscreen-close:hover {
  background: rgba(167, 139, 250, 0.12);
  color: #c4b5fd;
}

.mermaid-fullscreen-diagram :deep(svg) {
  max-width: 80vw;
  max-height: 80vh;
  height: auto;
}

.mermaid-fullscreen-diagram :deep(svg foreignObject),
.mermaid-fullscreen-diagram :deep(svg foreignObject *),
.mermaid-fullscreen-diagram :deep(svg .nodeLabel),
.mermaid-fullscreen-diagram :deep(svg .edgeLabel),
.mermaid-fullscreen-diagram :deep(svg text) {
  color: #000 !important;
  fill: #000 !important;
}
</style>
