<template>
  <div class="home-hero">
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 240 64"
      fill="none"
      class="home-logo"
      role="img"
      aria-label="chatrag.app"
    >
      <defs>
        <linearGradient id="logo-grad1" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style="stop-color:#c084fc;stop-opacity:1" />
          <stop offset="50%" style="stop-color:#818cf8;stop-opacity:1" />
          <stop offset="100%" style="stop-color:#38bdf8;stop-opacity:1" />
        </linearGradient>
        <linearGradient id="logo-grad2" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" style="stop-color:#a78bfa;stop-opacity:1" />
          <stop offset="100%" style="stop-color:#60a5fa;stop-opacity:1" />
        </linearGradient>
        <filter id="logo-glow">
          <feGaussianBlur stdDeviation="2" result="coloredBlur" />
          <feMerge>
            <feMergeNode in="coloredBlur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <!-- Icon: stylized chat bubble with nodes -->
      <g transform="translate(4, 6)">
        <!-- Chat bubble -->
        <rect x="2" y="2" width="44" height="36" rx="10" ry="10" fill="url(#logo-grad1)" opacity="0.9" />
        <polygon points="14,38 22,48 28,38" fill="url(#logo-grad1)" opacity="0.9" />
        <!-- RAG nodes inside bubble -->
        <circle cx="15" cy="16" r="4" fill="#0b0f1a" opacity="0.7" />
        <circle cx="33" cy="16" r="4" fill="#0b0f1a" opacity="0.7" />
        <circle cx="24" cy="28" r="4" fill="#0b0f1a" opacity="0.7" />
        <!-- Connecting lines -->
        <line x1="15" y1="16" x2="33" y2="16" stroke="#0b0f1a" stroke-width="1.5" opacity="0.4" />
        <line x1="15" y1="16" x2="24" y2="28" stroke="#0b0f1a" stroke-width="1.5" opacity="0.4" />
        <line x1="33" y1="16" x2="24" y2="28" stroke="#0b0f1a" stroke-width="1.5" opacity="0.4" />
        <!-- Bright centers -->
        <circle cx="15" cy="16" r="2" fill="#e0e7ff" />
        <circle cx="33" cy="16" r="2" fill="#e0e7ff" />
        <circle cx="24" cy="28" r="2" fill="#e0e7ff" />
      </g>
      <!-- Text -->
      <text
        x="62"
        y="42"
        font-family="system-ui, -apple-system, 'Segoe UI', sans-serif"
        font-size="36"
        font-weight="700"
        letter-spacing="-1"
        filter="url(#logo-glow)"
      >
        <tspan fill="url(#logo-grad2)">chat</tspan><tspan fill="#38bdf8">rag</tspan><tspan fill="#64748b" font-size="28" font-weight="400">.app</tspan>
      </text>
    </svg>
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
  margin: 0px auto 16px;
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
