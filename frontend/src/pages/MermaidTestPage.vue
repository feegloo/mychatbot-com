<template>
  <!--
    Dev-only test harness for MermaidBlock. Mounted only when import.meta.env.DEV
    is true (see router.ts). Accepts mermaid source via the `code` query
    parameter, base64-encoded as `codeB64`, or selects one of a few named
    fixtures via `fixture=valid|invalid|empty`. Used by the Playwright e2e
    suite to exercise rendering, error handling, and mode toggling without
    needing a live backend or assistant stream.
  -->
  <div class="mermaid-test-page">
    <h1>MermaidBlock test harness</h1>
    <p class="hint">Dev-only page used by e2e tests.</p>
    <MermaidBlock :key="resolvedCode" :code="resolvedCode" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import MermaidBlock from '../components/MermaidBlock.vue'

const FIXTURES: Record<string, string> = {
  valid: `graph TD
  A[Start] --> B{Is it?}
  B -->|Yes| C[OK]
  B -->|No| D[End]`,
  invalid: `graph TD\n  this is not valid mermaid @@ !! ???`,
  empty: '',
}

const route = useRoute()

const resolvedCode = computed<string>(() => {
  const q = route.query
  const fixture = typeof q.fixture === 'string' ? q.fixture : ''
  if (fixture && fixture in FIXTURES) return FIXTURES[fixture]

  const codeB64 = typeof q.codeB64 === 'string' ? q.codeB64 : ''
  if (codeB64) {
    try {
      return atob(codeB64)
    } catch {
      return ''
    }
  }

  const code = typeof q.code === 'string' ? q.code : ''
  return code || FIXTURES.valid
})
</script>

<style scoped>
.mermaid-test-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 24px;
  color: #e2e8f0;
}

h1 {
  font-size: 18px;
  margin: 0 0 4px;
}

.hint {
  font-size: 12px;
  color: #94a3b8;
  margin: 0 0 16px;
}
</style>
