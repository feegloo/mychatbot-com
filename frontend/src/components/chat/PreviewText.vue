<script setup lang="ts">
/**
 * Fallback tile for any non-image, non-PDF attachment (docx, txt, csv…).
 * Shows a generic document icon + filename. Click bubbles to parent.
 */
defineProps<{ name: string }>()
const emit = defineEmits<{ open: [] }>()
</script>

<template>
  <div class="preview-text" @click="emit('open')">
    <svg
      width="48"
      height="48"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.5"
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
    </svg>
    <span>{{ name }}</span>
  </div>
</template>

<style scoped>
.preview-text {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  height: 100%;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.7);
  font-size: 12px;
  text-align: center;
  padding: 12px;
  cursor: pointer;
}
</style>
