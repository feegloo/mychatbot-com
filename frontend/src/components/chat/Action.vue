<script setup lang="ts">
/**
 * Plain suggested-question pill. Emits the label on click so the parent
 * can submit it as a new question. Visual style: neutral pill, no icon.
 */
import { computed } from 'vue'
import { marked } from 'marked'

const props = defineProps<{ label: string }>()
const emit = defineEmits<{ select: [label: string] }>()

const renderedLabel = computed(() => marked.parseInline(props.label) as string)
</script>

<template>
  <!-- eslint-disable-next-line vue/no-v-html -- renderedLabel is inline markdown parsed from static action labels, no user HTML input -->
  <button class="action" type="button" @click="emit('select', label)" v-html="renderedLabel" />
</template>

<style scoped>
.action {
  position: relative;
  display: inline-block;
  padding: 6px 12px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  color: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
}
.action::after {
  content: '';
  position: absolute;
  bottom: -7px;
  left: 11px;
  width: 8px;
  height: 7px;
  background: rgba(167, 139, 250, 0.35);
  clip-path: polygon(0 0, 100% 0, 3% 100%);
  pointer-events: none;
  transition: background 0.15s;
}
.action:hover {
  background: rgba(255, 255, 255, 0.1);
}
.action:hover::after {
  background: rgba(167, 139, 250, 0.55);
}
.action :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.85em;
  background: rgba(255, 255, 255, 0.12);
  border-radius: 3px;
  padding: 1px 4px;
}
</style>
