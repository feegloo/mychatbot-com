<template>
  <span class="uploading-dots"
    >{{ labelText
    }}<span v-for="i in 3" :key="i" class="dot" :style="{ animationDelay: `${(i - 1) * 0.3}s` }"
      >.</span
    ></span
  >
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ text?: string }>()
const labelText = computed(() => props.text || 'Uploading')
</script>

<style scoped>
.uploading-dots {
  display: inline;
}
.dot {
  opacity: 0;
  animation: dotPulse 1.2s infinite;
}
@keyframes dotPulse {
  0%,
  20% {
    opacity: 0;
  }
  30%,
  70% {
    opacity: 1;
  }
  80%,
  100% {
    opacity: 0;
  }
}
</style>
