<template>
  <button
    class="home-lang-toggle"
    :title="t.switchTitle"
    :aria-label="t.switchTitle"
    @click="toggleHomeLang"
  >
    <span class="home-lang-flag">{{ flag }}</span>
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { homeLang, homeT, toggleHomeLang } from '../i18n/homeLocale'

const t = homeT

// Show the flag of the currently active home-page language, mirroring
// LanguageToggle.vue (the user sees what is active, not what will activate).
const flag = computed(() => (homeLang.value === 'pl' ? '🇵🇱' : '🇬🇧'))
</script>

<style scoped>
.home-lang-toggle {
  position: absolute;
  top: 16px;
  right: 16px;
  z-index: 10;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 1px solid rgba(167, 139, 250, 0.25);
  border-radius: 10px;
  background: rgba(30, 27, 47, 0.6);
  cursor: pointer;
  transition:
    background 0.15s ease,
    border-color 0.15s ease,
    transform 0.15s ease;
}

.home-lang-toggle:hover {
  background: rgba(60, 50, 95, 0.7);
  border-color: rgba(167, 139, 250, 0.5);
}

.home-lang-toggle:active {
  transform: scale(0.96);
}

.home-lang-flag {
  font-size: 18px;
  line-height: 1;
}

@media (max-width: 768px) {
  .home-lang-toggle {
    top: 10px;
    right: 10px;
    width: 32px;
    height: 32px;
  }
}
</style>
