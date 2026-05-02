<template>
  <Teleport to="body">
    <div v-if="visible" class="wiki-modal-overlay" @click.self="$emit('close')">
      <div class="wiki-modal-content">
        <div class="wiki-modal-header">
          <span class="wiki-modal-title">
            {{ headerTitle }}
          </span>
          <button class="wiki-modal-close" aria-label="Close" title="Close" @click="$emit('close')">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div class="wiki-modal-body">
          <div v-if="loading" class="wiki-modal-loading">Loading…</div>
          <!-- Pre-rendered SVG (e.g. mindmap): display directly, no mermaid re-render -->
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div v-else-if="svgContent" class="mindmap-svg-container" v-html="svgContent" />
          <div v-else-if="!content" class="wiki-modal-empty">No wiki available yet.</div>
          <template v-else>
            <template v-for="(part, i) in parts" :key="i">
              <!-- eslint-disable-next-line vue/no-v-html -->
              <div v-if="part.type === 'text'" class="wiki-text" :class="{ 'wiki-text--first': i === 0 }" v-html="part.html" />
              <MermaidBlock v-else-if="part.type === 'mermaid'" :code="part.code" initial-zoom="max" />
            </template>
          </template>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { splitContent } from './chat/splitContent'

const MermaidBlock = defineAsyncComponent(() => import('./MermaidBlock.vue'))

const props = defineProps<{
  visible: boolean
  content: string | null
  svgContent?: string | null
  loading?: boolean
  title?: string
}>()

defineEmits<{
  close: []
}>()

const headerTitle = computed(() => {
  if (props.title) return `${props.title} — Knowledge Wiki 🗺️`
  return 'Knowledge Wiki 🗺️'
})

// Strip the auto-generated h1 "... — Internal Wiki" heading and the "## Domain" heading
// so the modal starts directly with the domain sentence.
const processedContent = computed(() => {
  if (!props.content) return null
  return props.content
    .replace(/^#[^\n]*—\s*Internal Wiki\s*\n+/m, '')
    .replace(/^##\s+Domain\s*\n/m, '')
})

const parts = computed(() => (processedContent.value ? splitContent(processedContent.value) : []))
</script>

<style scoped>
.wiki-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.72);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  box-sizing: border-box;
  cursor: pointer;
}

.wiki-modal-content {
  background: rgba(10, 13, 22, 0.92);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.09);
  border-radius: 16px;
  width: 100%;
  max-width: 920px;
  max-height: 87vh;
  display: flex;
  flex-direction: column;
  box-shadow:
    0 24px 64px rgba(0, 0, 0, 0.7),
    0 1px 0 rgba(255, 255, 255, 0.06) inset;
  cursor: default;
  overflow: hidden;
}

.wiki-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px 14px 22px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.03);
}

.wiki-modal-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.88);
  letter-spacing: 0.01em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.wiki-modal-close {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.45);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  margin-left: 12px;
}

@media (hover: hover) {
  .wiki-modal-close:hover {
    background: rgba(255, 255, 255, 0.1);
    color: rgba(255, 255, 255, 0.9);
  }
}

.wiki-modal-body {
  overflow-y: auto;
  padding: 22px 26px 28px;
  flex: 1;
  color: rgba(203, 213, 225, 0.9);
  font-size: 0.94rem;
  line-height: 1.72;
}

.wiki-modal-loading,
.wiki-modal-empty {
  color: rgba(100, 116, 139, 0.8);
  text-align: center;
  padding: 48px 0;
}

/* First text block has no top margin so content starts flush */
.wiki-text--first :deep(h1:first-child),
.wiki-text--first :deep(h2:first-child),
.wiki-text--first :deep(h3:first-child),
.wiki-text--first :deep(p:first-child) {
  margin-top: 0;
}

.wiki-text :deep(h1),
.wiki-text :deep(h2),
.wiki-text :deep(h3) {
  color: rgba(241, 245, 249, 0.95);
  margin-top: 1.4em;
  margin-bottom: 0.45em;
  font-weight: 600;
  letter-spacing: 0.01em;
}

.wiki-text :deep(h2) {
  font-size: 1.05rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.07);
  padding-bottom: 0.3em;
}

.wiki-text :deep(h3) {
  font-size: 0.97rem;
  color: rgba(148, 163, 184, 0.9);
}

.wiki-text :deep(p) {
  margin-bottom: 0.8em;
}

.wiki-text :deep(ul),
.wiki-text :deep(ol) {
  padding-left: 1.5em;
  margin-bottom: 0.8em;
}

.wiki-text :deep(li) {
  margin-bottom: 0.3em;
}

.wiki-text :deep(strong) {
  color: rgba(226, 232, 240, 0.95);
  font-weight: 600;
}

.wiki-text :deep(a) {
  color: #60a5fa;
}

.wiki-text :deep(code) {
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 0.86em;
}

.wiki-text :deep(pre) {
  background: rgba(0, 0, 0, 0.4);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 8px;
  padding: 14px;
  overflow-x: auto;
  margin-bottom: 1em;
}

.mindmap-svg-container {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px;
  box-sizing: border-box;
  background: rgba(248, 250, 252, 0.05);
  border-radius: 8px;
}

.mindmap-svg-container :deep(svg) {
  width: 100%;
  height: auto;
  max-height: 68vh;
}
</style>
