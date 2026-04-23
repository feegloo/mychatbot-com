<script setup lang="ts">
/**
 * Image preview tile. Renders <img> with lazy-loading; clicking delegates
 * to the parent so a single shared `<ImageModal>` can be opened at the
 * top of ChatMessage.
 */
defineProps<{ url: string; name: string }>()
const emit = defineEmits<{ open: [] }>()
</script>

<template>
  <div class="preview-img" @click="emit('open')">
    <img :src="url" :alt="name" loading="lazy" />
  </div>
</template>

<style scoped>
.preview-img {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  cursor: zoom-in;
  overflow: hidden;
  border-radius: 8px;
}
.preview-img img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}
</style>
