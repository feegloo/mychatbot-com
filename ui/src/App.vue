<template>
  <div class="app-shell">
    <aside class="menu-column" aria-label="Left menu"></aside>
    <main class="content-column" aria-label="Main content">
      <HomeHero />
      <p class="hello-world-message" data-testid="hello-world-message">{{ helloMessage }}</p>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import HomeHero from '@frontend-home-hero'

const helloMessage = ref('')

onMounted(async () => {
  const res = await fetch('/api2/hello-world')
  const data = await res.json()
  helloMessage.value = data.message
})
</script>

<style lang="css" scoped>
.app-shell {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  min-height: 100vh;
}

.menu-column {
  background: var(--menu-column-bg);
}

.content-column {
  background: var(--content-column-bg);
  overflow: auto;
}

.content-column > * {
  min-height: 100%;
}

@media (max-width: 768px) {
  .app-shell {
    grid-template-columns: 1fr;
    grid-template-rows: 120px minmax(0, 1fr);
  }

  .menu-column {
    min-height: 120px;
  }
}
</style>
