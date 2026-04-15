<template>
  <svg class="bubble-tip" :width="width" :height="height" :viewBox="`0 0 ${width} ${height}`" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path :d="`M${width} 0 C${width} 0, ${width * 0.15} ${height * 0.25}, 0 ${height} C${width * 0.45} ${height * 0.55}, ${width * 0.65} ${height * 0.25}, ${width} 0Z`" fill="currentColor" />
  </svg>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ width?: number; height?: number }>(), {
  width: 10,
  height: 10,
});
</script>
