<script setup lang="ts">
/**
 * Overflow group for `[action:Label]` items beyond the visible-action
 * limit (welcome: 2, regular: 1). Uses floating-vue `VDropdown` for
 * positioning + outside-click handling so we don't reinvent the wheel.
 */
import MessageContentAction from './MessageContentAction.vue'

defineProps<{ actions: string[] }>()
const emit = defineEmits<{ select: [label: string] }>()
</script>

<template>
  <VDropdown v-if="actions.length" :distance="6">
    <button class="more-btn" type="button">More… ({{ actions.length }})</button>
    <template #popper>
      <div class="more-menu">
        <MessageContentAction
          v-for="label in actions"
          :key="label"
          :label="label"
          @select="emit('select', $event)"
        />
      </div>
    </template>
  </VDropdown>
</template>

<style scoped>
.more-btn {
  display: inline-block;
  padding: 6px 12px;
  border: 1px dashed rgba(255, 255, 255, 0.25);
  border-radius: 999px;
  background: transparent;
  color: inherit;
  font-size: 13px;
  cursor: pointer;
}
.more-btn:hover {
  background: rgba(255, 255, 255, 0.06);
}
.more-menu {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  min-width: 180px;
}
</style>
