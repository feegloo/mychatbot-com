<template>
  <Teleport to="body">
    <div v-if="visible" class="image-modal-overlay" @click.self="$emit('close')">
      <div class="image-modal-content">
        <button class="image-modal-close" @click="$emit('close')">&times;</button>
        <img :src="src" :alt="alt" class="image-modal-img" />
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
defineProps<{
  visible: boolean;
  src: string;
  alt?: string;
}>();

defineEmits<{
  close: [];
}>();
</script>

<style scoped>
.image-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.image-modal-content {
  position: relative;
  max-width: 90vw;
  max-height: 90vh;
  cursor: default;
}

.image-modal-close {
  position: absolute;
  top: -12px;
  right: -12px;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  background: #1e293b;
  color: #e2e8f0;
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
  transition: background 0.15s;
}

@media (hover: hover) {
  .image-modal-close:hover {
    background: #334155;
  }
}
.image-modal-close:active {
  background: #334155;
}

.image-modal-img {
  max-width: 90vw;
  max-height: 85vh;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  object-fit: contain;
}
</style>
