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
      <!-- eslint-disable vue/no-v-html -->
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
      <!-- eslint-enable vue/no-v-html -->
      <br />
      <span class="home-subtitle-extra">{{ t.subtitleP3 }}</span>
    </p>
    <!-- <div class="home-download">
      <svg class="home-download-icon" xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"/>
      </svg>
      <span class="home-download-label">macOS —</span>
      <a
        href="https://github.com/feegloo/chatrag-app/releases/latest/download/ChatRAG-arm64.dmg"
        class="home-download-link"
        target="_blank"
        rel="noopener noreferrer"
        title="Apple Silicon (M1/M2/M3)"
      >Apple Silicon</a>
      <span class="home-download-sep">·</span>
      <a
        href="https://github.com/feegloo/chatrag-app/releases/latest/download/ChatRAG-x64.dmg"
        class="home-download-link"
        target="_blank"
        rel="noopener noreferrer"
        title="Apple Intel (x86_64)"
      >Intel</a>
      <span class="home-download-sep home-download-sep--subtle">— download ChatRAG.app <span class="home-download-badge">online / offline</span></span>
    </div> -->
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
  margin: 0px auto;
  filter: drop-shadow(0 0 24px rgba(167, 139, 250, 0.3));
  position: relative;
  top: 6px;
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

.home-download {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 14px;
  font-size: 13px;
  color: #64748b;
}

.home-download-icon {
  color: #94a3b8;
  flex-shrink: 0;
  margin-right: 1px;
}

.home-download-label {
  color: #64748b;
}

.home-download-link {
  color: #a78bfa;
  text-decoration: none;
  font-weight: 500;
  transition: color 0.15s;
}

.home-download-link:hover {
  color: #c4b5fd;
  text-decoration: underline;
}

.home-download-sep {
  color: #475569;
}

.home-download-sep--subtle {
  color: #64748b;
}

.home-download-badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 10px;
  background: rgba(167, 139, 250, 0.12);
  color: #a78bfa;
  border: 1px solid rgba(167, 139, 250, 0.2);
  vertical-align: middle;
  margin-left: 2px;
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
