<script setup lang="ts">
/**
 * Action prompt pill — corresponds to `[action:Label]` in message content.
 * Visually emphasized vs <Action> (plain prompts) to signal a different
 * intent (e.g. "Make diagram 📊").
 */
defineProps<{ label: string }>()
const emit = defineEmits<{ select: [label: string] }>()
</script>

<template>
  <button class="message-content-action" type="button" @click="emit('select', label)">
    {{ label }}
  </button>
</template>

<style scoped>
.message-content-action {
  position: relative;
  text-align: left;
  display: inline-block;
  padding: 6px 12px;
  border: 1px solid rgba(147, 51, 234, 0.4);
  border-radius: 999px;
  background: transparent;
  color: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
}
.message-content-action::after {
  content: '';
  position: absolute;
  bottom: -7px;
  left: 11px;
  width: 8px;
  height: 7px;
  background: rgba(147, 51, 234, 0.4);
  clip-path: polygon(0 0, 100% 0, 3% 100%);
  pointer-events: none;
  transition: background 0.15s;
}
.message-content-action:hover {
  background: rgba(147, 51, 234, 0.22);
}
.message-content-action:hover::after {
  background: rgba(147, 51, 234, 0.6);
}
</style>
