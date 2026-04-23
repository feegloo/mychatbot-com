<script setup lang="ts">
/**
 * Plain suggested-question pill. Emits the label on click so the parent
 * can submit it as a new question. Visual style: neutral pill, no icon.
 */
defineProps<{ label: string }>()
const emit = defineEmits<{ select: [label: string] }>()
</script>

<template>
  <button class="action" type="button" @click="emit('select', label)">{{ label }}</button>
</template>

<style scoped>
.action {
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
.action:hover {
  background: rgba(255, 255, 255, 0.1);
}
</style>
