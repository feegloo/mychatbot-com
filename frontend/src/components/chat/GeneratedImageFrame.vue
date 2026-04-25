<script setup lang="ts">
import type { CSSProperties } from 'vue'

const props = withDefaults(
  defineProps<{
    src: string
    alt?: string
    imageStyle?: CSSProperties
  }>(),
  {
    alt: 'Generated image',
    imageStyle: undefined,
  },
)

const emit = defineEmits<{
  load: [event: Event]
  error: [event: Event]
}>()
</script>

<template>
  <div class="generated-image-frame">
    <img
      :src="props.src"
      :alt="props.alt"
      :style="props.imageStyle"
      class="generated-image"
      @load="emit('load', $event)"
      @error="emit('error', $event)"
    />
  </div>
</template>

<style scoped>
.generated-image-frame {
  border-radius: 12px;
  overflow: hidden;
}

.generated-image {
  display: block;
  width: 100%;
  height: auto;
}
</style>
