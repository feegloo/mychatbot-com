<template>
  <!-- Embed mode: no sidebar, no nav, no toggle -->
  <router-view v-if="isEmbed" :key="$route.fullPath" />

  <!-- Normal mode -->
  <div v-else class="app-layout">
    <div class="sidebar-overlay" :class="{ open: sidebarOpen }" @click="sidebarOpen = false"></div>
    <ConversationNav :class="{ open: sidebarOpen }" @navigate="sidebarOpen = false" />
    <main class="app-main">
      <button class="sidebar-toggle" @click="sidebarOpen = !sidebarOpen" aria-label="Toggle menu">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
      </button>
      <router-view :key="$route.fullPath" />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import ConversationNav from "./components/ConversationNav.vue";
import { getBrowserFingerprint, getUserId, setUserId } from "./utils/fingerprint";
import { resolveFingerprint } from "./api";

const sidebarOpen = ref(false);
const route = useRoute();
const isEmbed = computed(() => route.meta.embed === true);

watch(() => route.path, () => { sidebarOpen.value = false; });

// Initialize fingerprint and resolve userId on app start
onMounted(async () => {
  try {
    if (getUserId() !== null) return; // already resolved
    const fingerprint = await getBrowserFingerprint();
    const { userId } = await resolveFingerprint(fingerprint);
    setUserId(userId);
  } catch (err) {
    console.error("[fingerprint init]", err);
  }
});
</script>
