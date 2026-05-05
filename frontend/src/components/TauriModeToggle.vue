<template>
  <div v-if="isTauri" class="tauri-mode-bar" role="region" aria-label="App mode">
    <div class="tauri-mode-bar__row">
      <span
        class="tauri-mode-bar__label"
        :class="{ 'tauri-mode-bar__label--active': mode === 'cloud' }"
        @mouseenter="scheduleTooltip('cloud')"
        @mouseleave="cancelTooltip"
      >Cloud</span>

      <button
        class="tauri-apple-switch"
        :class="{ 'tauri-apple-switch--local': mode === 'local' }"
        role="switch"
        :aria-checked="mode === 'local'"
        :aria-label="mode === 'cloud' ? 'Switch to local mode' : 'Switch to cloud mode'"
        @click="toggle"
      >
        <span class="tauri-apple-switch__thumb" />
      </button>

      <span
        class="tauri-mode-bar__label"
        :class="{ 'tauri-mode-bar__label--active': mode === 'local' }"
        @mouseenter="scheduleTooltip('local')"
        @mouseleave="cancelTooltip"
      >Local</span>
    </div>

    <Transition name="tauri-tooltip">
      <div v-if="tooltipText" class="tauri-mode-bar__tooltip" role="tooltip">
        {{ tooltipText }}
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted } from 'vue'
import { useTauriMode, type AppMode } from '../composables/useTauriMode'

const { isTauri, mode, setMode } = useTauriMode()

const tooltipText = ref<string | null>(null)
let tooltipTimer: ReturnType<typeof setTimeout> | null = null

const TOOLTIPS: Record<AppMode, string> = {
  cloud: 'use LLM (models) from chatrag.app',
  local: 'use private LLM (models) — "offline mode"',
}

function toggle() {
  setMode(mode.value === 'cloud' ? 'local' : 'cloud')
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

onUnmounted(cancelTooltip)
</script>

<style scoped>
/* ── Floating bar ─────────────────────────────────────────────────────────── */
.tauri-mode-bar {
  position: fixed;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  pointer-events: none; /* let clicks fall through except on the row itself */
}

.tauri-mode-bar__row {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(20, 24, 36, 0.82);
  backdrop-filter: blur(12px) saturate(1.6);
  -webkit-backdrop-filter: blur(12px) saturate(1.6);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 999px;
  padding: 5px 12px;
  pointer-events: auto;
  box-shadow:
    0 2px 8px rgba(0, 0, 0, 0.45),
    0 0 0 0.5px rgba(255, 255, 255, 0.06) inset;
}

/* ── Labels ───────────────────────────────────────────────────────────────── */
.tauri-mode-bar__label {
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.01em;
  color: rgba(255, 255, 255, 0.38);
  transition: color 0.22s ease;
  user-select: none;
  cursor: default;
  line-height: 1;
}

.tauri-mode-bar__label--active {
  color: rgba(255, 255, 255, 0.88);
}

/* ── Apple-style switch ───────────────────────────────────────────────────── */
.tauri-apple-switch {
  position: relative;
  width: 44px;
  height: 26px;
  border-radius: 999px;
  background: #007aff; /* Apple blue — cloud / "on" */
  border: none;
  cursor: pointer;
  padding: 0;
  outline: none;
  transition:
    background 0.25s ease,
    box-shadow 0.15s ease;
  box-shadow: 0 0 0 2px rgba(0, 122, 255, 0.35);
  flex-shrink: 0;
}

.tauri-apple-switch:focus-visible {
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.6);
}

.tauri-apple-switch--local {
  background: #34c759; /* Apple green — local / "off" */
  box-shadow: 0 0 0 2px rgba(52, 199, 89, 0.35);
}

.tauri-apple-switch--local:focus-visible {
  box-shadow: 0 0 0 3px rgba(52, 199, 89, 0.6);
}

/* Thumb */
.tauri-apple-switch__thumb {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.25s cubic-bezier(0.34, 1.2, 0.64, 1);
  box-shadow:
    0 1px 4px rgba(0, 0, 0, 0.3),
    0 0 0 0.5px rgba(0, 0, 0, 0.08);
  pointer-events: none;
}

.tauri-apple-switch--local .tauri-apple-switch__thumb {
  transform: translateX(18px);
}

/* ── Tooltip ──────────────────────────────────────────────────────────────── */
.tauri-mode-bar__tooltip {
  font-size: 11.5px;
  color: rgba(255, 255, 255, 0.82);
  background: rgba(20, 24, 36, 0.9);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  padding: 5px 10px;
  pointer-events: none;
  white-space: nowrap;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.4);
}

/* Tooltip transition */
.tauri-tooltip-enter-active,
.tauri-tooltip-leave-active {
  transition:
    opacity 0.18s ease,
    transform 0.18s ease;
}

.tauri-tooltip-enter-from,
.tauri-tooltip-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
