<template>
  <Teleport to="body">
    <div v-if="visible" class="image-modal-overlay" @click.self="$emit('close')">
      <div class="image-modal-content">
        <button
          type="button"
          class="image-modal-close"
          aria-label="Close image"
          title="Close image"
          @click="$emit('close')"
        >
          &times;
        </button>
        <Transition name="modal-img-fade" mode="out-in">
          <img :key="src" :src="src" :alt="alt" class="image-modal-img" :class="{ 'image-modal-img--stretch': stretch }" />
        </Transition>
        <Transition name="modal-title-fade">
          <div v-if="title" :key="title" class="image-modal-title">"{{ title }}"</div>
        </Transition>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
defineProps<{
  visible: boolean
  src: string
  alt?: string
  title?: string
  /** When true: mobile fills full width, desktop fills full height (for SVG/diagrams) */
  stretch?: boolean
}>()

defineEmits<{
  close: []
}>()
</script>

<style scoped>
.image-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.9);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.image-modal-content {
  position: relative;
  max-width: 90vw;
  max-height: 100vh;
  cursor: default;
  display: flex;
  flex-direction: column;
}

.image-modal-close {
  position: absolute;
  top: 2px;
  right: -33px;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  border: none;
  color: white;
  background: transparent;
  font-size: 32px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
}

@media (hover: hover) {
  .image-modal-close:hover {
    background: #334155;
  }
}
.image-modal-close:active {
  background: #334155;
}

/* On mobile: show button in-flow above the image, aligned right */
@media (max-width: 768px) {
  .image-modal-content {
    max-width: 100vw;
  }

  .image-modal-close {
    position: static;
    align-self: flex-end;
    margin-bottom: 4px;
    flex-shrink: 0;
  }

  .image-modal-img {
    max-width: 100vw;
  }
}

.image-modal-img {
  max-width: 90vw;
  max-height: 100vh;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  object-fit: contain;
  display: block;
}

/* Stretch mode: SVG/diagrams — mobile fills full width, desktop fills full height */
.image-modal-img--stretch {
  width: 100vw;
  max-width: 100vw;
  height: auto;
  max-height: 95vh;
}

@media (min-width: 769px) {
  .image-modal-img--stretch {
    width: auto;
    max-width: 95vw;
    height: 95vh;
    max-height: 95vh;
  }
}

/* Fade transition when src changes (morph progression) */
.modal-img-fade-enter-active,
.modal-img-fade-leave-active {
  transition: opacity 0.3s ease;
}
.modal-img-fade-enter-from,
.modal-img-fade-leave-to {
  opacity: 0;
}

/* Title overlay at bottom of image */
.image-modal-title {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 14px 20px 16px;
  color: #fff;
  font-size: 15px;
  line-height: 1.4;
  text-align: center;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.65));
  border-radius: 0 0 4px 4px;
  pointer-events: none;
}

.modal-title-fade-enter-active {
  transition:
    opacity 0.5s ease 0.15s,
    transform 0.5s ease 0.15s;
}
.modal-title-fade-leave-active {
  transition: opacity 0.2s ease;
}
.modal-title-fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.modal-title-fade-leave-to {
  opacity: 0;
}
.modal-title-fade-enter-to,
.modal-title-fade-leave-from {
  opacity: 1;
  transform: translateY(0);
}
</style>
