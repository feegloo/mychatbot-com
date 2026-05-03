<script setup lang="ts">
/**
 * Overflow group for `[action:Label]` items beyond the visible-action
 * limit (welcome: up to 5 depending on visible prompts, regular: 3). Uses floating-vue `VDropdown` for
 * positioning + outside-click handling so we don't reinvent the wheel.
 */
import MessageContentAction from './MessageContentAction.vue'

defineProps<{ actions: string[] }>()
const emit = defineEmits<{ select: [label: string] }>()
</script>

<template>
  <VDropdown v-if="actions.length" theme="more-questions" :distance="6">
    <button class="more-btn" type="button">More… ({{ actions.length }})</button>
    <template #popper="{ hide }">
      <div class="more-actions-popper">
        <MessageContentAction
          v-for="label in actions"
          :key="label"
          :label="label"
          @select="(value) => { emit('select', value); hide() }"
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
</style>
