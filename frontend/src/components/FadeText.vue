<script setup lang="ts">
import { appReady } from '../composables/appReady'

/**
 * Wraps a block of content (typically assistant text) with a fade-out /
 * fade-in transition driven by a `trigger` prop. When `trigger` changes
 * Vue unmounts the previous child and mounts a new one, so the
 * transition plays automatically without any watchers or manual
 * animation bookkeeping.
 *
 * The appear animation is gated on `appReady` so the initial page load
 * (restored conversation history) renders instantly instead of flashing
 * every message in.
 *
 * A slot is used instead of a string prop so call sites keep their
 * existing template refs (e.g. `contentEls` for tooltip attachment) and
 * event handlers intact.
 */
defineProps<{
  trigger: string | number
}>()
</script>

<template>
  <Transition name="fade-text" mode="out-in" :appear="appReady">
    <div :key="trigger" class="fade-text">
      <slot />
    </div>
  </Transition>
</template>

<style>
.fade-text-enter-active,
.fade-text-leave-active {
  transition: opacity 0.25s ease;
}
.fade-text-enter-from,
.fade-text-leave-to {
  opacity: 0;
}
</style>
