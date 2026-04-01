<template>
  <div class="app-layout">
    <ConversationNav />
    <main class="app-main">
      <router-view :key="$route.fullPath" />
    </main>
  </div>
</template>

<script setup lang="ts">
import ConversationNav from "./components/ConversationNav.vue";
</script>
