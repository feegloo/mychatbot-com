<template>
  <div class="app-shell" data-testid="app-shell">
    <aside class="menu-column" data-testid="menu-column" aria-label="Left menu"></aside>
    <main
      class="content-column"
      data-testid="content-column"
      aria-label="Main content"
    >
      <HomeHero />
    </main>
  </div>
</template>

<script setup lang="ts">
import HomeHero from '@frontend-home-hero'
</script>
