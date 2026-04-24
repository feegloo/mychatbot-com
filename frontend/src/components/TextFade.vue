<script setup lang="ts">
import { newContent } from '../composables/newContent';

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
  disabled?: boolean
}>()
</script>

<template>
  <Transition :name="disabled ? '' : 'fade-text'" mode="out-in" :appear="!disabled && newContent">
    <div :key="trigger" class="fade-text">
      <slot />
    </div>
  </Transition>
</template>

<style>
/*
 * Fade via `color` rather than `opacity` so inline images (and other
 * non-text content) stay fully visible throughout the transition — only
 * the translated text animates. `*` is needed because descendants like
 * links or code spans set their own `color`, which wouldn't otherwise
 * fade alongside the wrapper's color.
 */
.fade-text-enter-active,
.fade-text-enter-active *,
.fade-text-leave-active,
.fade-text-leave-active * {
  transition: color 0.25s ease;
}
.fade-text-enter-from,
.fade-text-enter-from *,
.fade-text-leave-to,
.fade-text-leave-to * {
  color: transparent !important;
}
</style>
