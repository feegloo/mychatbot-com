<template>
  <Teleport to="body">
    <div v-if="visible" class="wiki-modal-overlay" @click.self="$emit('close')">
      <div class="wiki-modal-content">
        <div class="wiki-modal-header">
          <span class="wiki-modal-title">{{ title || '🗺️ Knowledge Wiki' }}</span>
          <button class="wiki-modal-close" title="Close" @click="$emit('close')">&times;</button>
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
              <div v-if="part.type === 'text'" class="wiki-text" v-html="part.html" />
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

const parts = computed(() => (props.content ? splitContent(props.content) : []))
</script>

<style scoped>
.wiki-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.75);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  box-sizing: border-box;
  cursor: pointer;
}

.wiki-modal-content {
  background: #1e293b;
  border-radius: 12px;
  width: 100%;
  max-width: 900px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6);
  cursor: default;
  overflow: hidden;
}

.wiki-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #334155;
  flex-shrink: 0;
}

.wiki-modal-title {
  font-size: 1.1rem;
  font-weight: 600;
  color: #f1f5f9;
}

.wiki-modal-close {
  background: transparent;
  border: none;
  color: #94a3b8;
  font-size: 28px;
  line-height: 1;
  cursor: pointer;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
}

@media (hover: hover) {
  .wiki-modal-close:hover {
    background: #334155;
    color: #f1f5f9;
  }
}

.wiki-modal-body {
  overflow-y: auto;
  padding: 24px;
  flex: 1;
  color: #cbd5e1;
  font-size: 0.95rem;
  line-height: 1.7;
}

.wiki-modal-loading,
.wiki-modal-empty {
  color: #64748b;
  text-align: center;
  padding: 40px 0;
}

.wiki-text :deep(h1),
.wiki-text :deep(h2),
.wiki-text :deep(h3) {
  color: #f1f5f9;
  margin-top: 1.25em;
  margin-bottom: 0.5em;
}

.wiki-text :deep(p) {
  margin-bottom: 0.75em;
}

.wiki-text :deep(ul),
.wiki-text :deep(ol) {
  padding-left: 1.5em;
  margin-bottom: 0.75em;
}

.wiki-text :deep(a) {
  color: #60a5fa;
}

.wiki-text :deep(code) {
  background: #0f172a;
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 0.88em;
}

.wiki-text :deep(pre) {
  background: #0f172a;
  border-radius: 8px;
  padding: 12px;
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
  background: #f8fafc;
  border-radius: 8px;
}

.mindmap-svg-container :deep(svg) {
  width: 100%;
  height: auto;
  max-height: 68vh;
}
</style>
