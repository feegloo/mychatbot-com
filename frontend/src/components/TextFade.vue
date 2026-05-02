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
 *
 * Action and prompt buttons (.actions-row, .prompts-row) are excluded from
 * the color transition. Platform color emoji fonts (Apple Color Emoji,
 * Segoe UI Emoji, Noto Color Emoji) don't always re-render emoji glyphs
 * correctly when `color` transitions from transparent back to a visible
 * value, causing emoji labels to remain invisible until the next full
 * repaint (e.g. page refresh). Because action buttons are interactive
 * elements that should always be readable, they are rendered outside the
 * color-fade envelope entirely.
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
/* Override: keep action/prompt buttons and their contents at their normal
   color so emoji glyphs are never subject to the color-fade. */
.fade-text-enter-from .actions-row,
.fade-text-enter-from .actions-row *,
.fade-text-enter-from .prompts-row,
.fade-text-enter-from .prompts-row *,
.fade-text-leave-to .actions-row,
.fade-text-leave-to .actions-row *,
.fade-text-leave-to .prompts-row,
.fade-text-leave-to .prompts-row * {
  color: inherit !important;
}
</style>
