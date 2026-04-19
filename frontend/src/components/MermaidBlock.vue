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
      <button v-else class="mermaid-tool-btn" @click="mode = 'diagram'">
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
      <button class="mermaid-tool-btn" @click="copyCode">
        <svg
          v-if="!copied"
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
        <svg
          v-else
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <polyline points="20 6 9 17 4 12" />
        </svg>
        {{ copied ? 'Copied!' : 'Copy code' }}
      </button>
    </div>
    <div v-show="mode === 'diagram' && ready" ref="diagramEl" class="mermaid-diagram"></div>
    <div v-if="mode === 'diagram' && !ready" class="mermaid-loading">
      <span class="mermaid-loading-dot"></span>
      <span class="mermaid-loading-dot"></span>
      <span class="mermaid-loading-dot"></span>
    </div>
    <pre v-show="mode === 'text'" class="mermaid-source"><code>{{ code }}</code></pre>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue'
import type mermaidType from 'mermaid'

const props = defineProps<{ code: string }>()

const mode = ref<'diagram' | 'text'>('diagram')
const copied = ref(false)
const hovered = ref(false)
const ready = ref(false)
const diagramEl = ref<HTMLElement | null>(null)
let renderCounter = 0

let mermaid: typeof mermaidType | null = null

async function getMermaid() {
  if (mermaid) return mermaid
  const mod = await import('mermaid')
  mermaid = mod.default
  mermaid.initialize({
    startOnLoad: false,
    theme: 'dark',
    themeVariables: {
      darkMode: true,
      background: '#1e1e2e',
      primaryColor: '#7c3aed',
      primaryTextColor: '#e2e8f0',
      primaryBorderColor: '#7c3aed',
      lineColor: '#94a3b8',
      secondaryColor: '#334155',
      tertiaryColor: '#1e293b',
    },
    flowchart: { htmlLabels: true, curve: 'basis' },
    securityLevel: 'strict',
  })
  return mermaid
}

async function renderDiagram() {
  if (!diagramEl.value) return
  ready.value = false
  try {
    const m = await getMermaid()
    const id = `mermaid-${Date.now()}-${renderCounter++}`
    const { svg } = await m.render(id, props.code)
    diagramEl.value.innerHTML = svg
    // Wait one frame so the browser paints the SVG before revealing
    requestAnimationFrame(() => {
      ready.value = true
    })
  } catch {
    // If mermaid render fails, fall back to text mode
    mode.value = 'text'
    ready.value = true
  }
}

function copyCode() {
  navigator.clipboard.writeText(props.code)
  copied.value = true
  setTimeout(() => {
    copied.value = false
  }, 2000)
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
  padding: 16px;
  display: flex;
  justify-content: center;
  overflow-x: auto;
}

.mermaid-diagram :deep(svg) {
  max-width: 100%;
  height: auto;
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
</style>
