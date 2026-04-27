<template>
  <div class="home-hero">
    <img src="/logo.svg" alt="chatrag.app" class="home-logo" />
    <p class="home-subtitle">
      <!-- v-html is safe here: content comes exclusively from the static
           homeMessages map under our control (no user input). -->
      <span v-html="t.subtitleP1Html"></span><br />
      <span v-html="t.subtitleP1bHtml"></span><br /><br />
      <span class="desktop-subtitle">
        <span v-html="t.subtitleP2Html"></span><br />
        <span v-html="t.subtitleP2bHtml"></span>
      </span>
      <span class="mobile-subtitle">
        <span v-html="t.subtitleP2MobileLine1Html"></span><br />
        <span v-html="t.subtitleP2MobileLine2Html"></span>
      </span>
      <br />
      <span class="home-subtitle-extra">{{ t.subtitleP3 }}</span>
    </p>
  </div>
</template>

<script setup lang="ts">
import { homeT } from '../i18n/homeLocale'

const t = homeT
</script>

<style scoped>
.home-hero {
  text-align: center;
  margin-bottom: 32px;
  flex-shrink: 0;
}

.home-logo {
  height: 52px;
  width: auto;
  display: block;
  margin: -10px auto 16px;
  filter: drop-shadow(0 0 24px rgba(167, 139, 250, 0.3));
}

.home-subtitle {
  color: #64748b;
  margin: 0;
  font-size: 15px;
  line-height: 1.5;
}

.home-subtitle-extra {
  font-size: 13px;
  margin-top: 12px;
  display: inline-block;
}

@media (max-width: 768px) {
  .home-logo {
    height: 40px;
  }

  .desktop-subtitle {
    display: none;
  }
}

@media (min-width: 769px) {
  .mobile-subtitle {
    display: none;
  }
}
</style>
