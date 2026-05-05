<template>
  <div v-if="!collapsed" class="settings-menu-wrap">
    <button
      ref="triggerRef"
      class="conv-nav-settings-btn"
      :class="{ active: open }"
      :aria-expanded="open"
      aria-label="Settings"
      title="Settings"
      @click.stop="open = !open"
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"/>
      </svg>
    </button>

    <Transition name="settings-pop">
      <div v-if="open" class="settings-menu" role="menu" @click.stop>
        <div class="settings-menu-header">Mode</div>

        <div class="settings-mode-row">
          <span
            class="settings-mode-label"
            :class="{ 'settings-mode-label--active': mode === 'cloud' }"
            @mouseenter="scheduleTooltip('cloud')"
            @mouseleave="cancelTooltip"
          >Cloud</span>

          <button
            class="settings-apple-switch"
            :class="{ 'settings-apple-switch--local': mode === 'local' }"
            role="switch"
            :aria-checked="mode === 'local'"
            :aria-label="mode === 'cloud' ? 'Switch to local mode' : 'Switch to cloud mode'"
            @click="handleToggle"
          >
            <span class="settings-apple-switch__thumb" />
          </button>

          <span
            class="settings-mode-label"
            :class="{ 'settings-mode-label--active': mode === 'local' }"
            @mouseenter="scheduleTooltip('local')"
            @mouseleave="cancelTooltip"
          >Local</span>
        </div>

        <Transition name="settings-tip">
          <p v-if="tooltipText" class="settings-mode-tip">{{ tooltipText }}</p>
        </Transition>
      </div>
    </Transition>

    <!-- Download prompt for browser users trying to switch to local -->
    <LocalDownloadModal :show="showDownloadModal" @close="showDownloadModal = false" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useTauriMode, type AppMode } from '../composables/useTauriMode'
import LocalDownloadModal from './LocalDownloadModal.vue'

defineProps<{ collapsed: boolean }>()

const { isTauri, mode, setMode } = useTauriMode()

const open = ref(false)
const showDownloadModal = ref(false)
const tooltipText = ref<string | null>(null)
let tooltipTimer: ReturnType<typeof setTimeout> | null = null

const TOOLTIPS: Record<AppMode, string> = {
  cloud: 'use LLM (models) from chatrag.app',
  local: 'use private LLM (models) — "offline mode"',
}

function handleToggle() {
  const next: AppMode = mode.value === 'cloud' ? 'local' : 'cloud'
  if (next === 'local' && !isTauri) {
    showDownloadModal.value = true
    return
  }
  setMode(next)
}

function scheduleTooltip(hoverMode: AppMode) {
  cancelTooltip()
  tooltipTimer = setTimeout(() => {
    tooltipText.value = TOOLTIPS[hoverMode]
  }, 1000)
}

function cancelTooltip() {
  if (tooltipTimer !== null) {
    clearTimeout(tooltipTimer)
    tooltipTimer = null
  }
  tooltipText.value = null
}

function onDocClick() {
  open.value = false
}

onMounted(() => document.addEventListener('click', onDocClick))
onUnmounted(() => {
  document.removeEventListener('click', onDocClick)
  cancelTooltip()
})
</script>

<style scoped>
.settings-menu-wrap {
  position: relative;
  flex-shrink: 0;
}

/* ── Trigger button ─────────────────────────────────────────────────────── */
.conv-nav-settings-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: 1px solid rgba(148, 163, 184, 0.36);
  background: rgba(15, 23, 42, 0.5);
  color: #94a3b8;
  border-radius: 10px;
  cursor: pointer;
  transition: color 0.2s, border-color 0.2s, background 0.2s;
}
.conv-nav-settings-btn:hover {
  color: #dbeafe;
  border-color: rgba(125, 211, 252, 0.8);
  background: rgba(15, 23, 42, 0.72);
}
.conv-nav-settings-btn.active {
  color: #e0f2fe;
  border-color: rgba(56, 189, 248, 0.85);
  background: rgba(14, 116, 144, 0.36);
  box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.22);
}

/* ── Popup menu ─────────────────────────────────────────────────────────── */
.settings-menu {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 0;
  min-width: 176px;
  background: #0f172a;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  padding: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  z-index: 200;
}

.settings-menu-header {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #475569;
  margin-bottom: 10px;
}

/* ── Mode row ───────────────────────────────────────────────────────────── */
.settings-mode-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.settings-mode-label {
  font-size: 12px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.38);
  transition: color 0.2s;
  user-select: none;
  cursor: default;
}
.settings-mode-label--active {
  color: rgba(255, 255, 255, 0.88);
}

/* ── Apple switch (reused styling) ─────────────────────────────────────── */
.settings-apple-switch {
  position: relative;
  width: 38px;
  height: 22px;
  border-radius: 999px;
  background: #007aff;
  border: none;
  cursor: pointer;
  padding: 0;
  outline: none;
  transition: background 0.25s ease, box-shadow 0.15s ease;
  box-shadow: 0 0 0 2px rgba(0, 122, 255, 0.3);
  flex-shrink: 0;
}
.settings-apple-switch:focus-visible {
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.55);
}
.settings-apple-switch--local {
  background: #34c759;
  box-shadow: 0 0 0 2px rgba(52, 199, 89, 0.3);
}
.settings-apple-switch--local:focus-visible {
  box-shadow: 0 0 0 3px rgba(52, 199, 89, 0.55);
}

.settings-apple-switch__thumb {
  position: absolute;
  top: 2.5px;
  left: 2.5px;
  width: 17px;
  height: 17px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.25s cubic-bezier(0.34, 1.2, 0.64, 1);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
  pointer-events: none;
}
.settings-apple-switch--local .settings-apple-switch__thumb {
  transform: translateX(16px);
}

/* ── Tooltip inside menu ────────────────────────────────────────────────── */
.settings-mode-tip {
  font-size: 11px;
  color: #64748b;
  margin: 8px 0 0;
  line-height: 1.4;
}

/* ── Transitions ────────────────────────────────────────────────────────── */
.settings-pop-enter-active,
.settings-pop-leave-active {
  transition: opacity 0.16s ease, transform 0.16s ease;
}
.settings-pop-enter-from,
.settings-pop-leave-to {
  opacity: 0;
  transform: translateY(6px) scale(0.97);
}

.settings-tip-enter-active,
.settings-tip-leave-active {
  transition: opacity 0.15s ease;
}
.settings-tip-enter-from,
.settings-tip-leave-to {
  opacity: 0;
}
</style>
