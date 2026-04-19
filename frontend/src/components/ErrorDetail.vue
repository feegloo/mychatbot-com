<template>
  <div class="error-detail" v-if="message">
    <p class="error-summary">{{ message }}</p>
    <div v-if="raw && raw !== message" class="error-raw-wrapper">
      <button class="error-toggle" @click="expanded = !expanded">
        {{ expanded ? '▾ Hide details' : '▸ Show details' }}
      </button>
      <pre v-if="expanded" class="error-raw">{{ raw }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";

defineProps<{
  message: string;
  raw?: string;
}>();

const expanded = ref(false);
</script>

<style scoped>
.error-detail {
  text-align: center;
  margin-top: 12px;
}
.error-summary {
  color: #f87171;
  margin: 0;
  word-break: break-word;
}
.error-raw-wrapper {
  margin-top: 4px;
}
.error-toggle {
  background: none;
  border: none;
  color: #888;
  cursor: pointer;
  font-size: 0.78em;
  padding: 2px 6px;
  font-family: inherit;
}
.error-toggle:hover {
  color: #bbb;
}
.error-raw {
  margin: 6px auto 0;
  max-width: 100%;
  max-height: 200px;
  overflow: auto;
  background: rgba(255, 50, 50, 0.08);
  border: 1px solid rgba(248, 113, 113, 0.25);
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 0.75em;
  color: #f87171;
  text-align: left;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
