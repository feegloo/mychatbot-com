<template>
  <div class="app-shell" data-testid="app-shell">
    <aside class="menu-column" data-testid="menu-column" aria-label="Left menu"></aside>
    <main class="content-column" data-testid="content-column" aria-label="Main content">
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
