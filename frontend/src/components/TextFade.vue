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

/*
 * Action and prompt button rows (.actions-row, .prompts-row) must never be
 * subject to `color: transparent`. Platform color emoji fonts (Apple Color
 * Emoji, Segoe UI Emoji, Noto Color Emoji) can get "stuck" invisible in some
 * browsers when `color` transitions from transparent back to a normal value,
 * because those fonts composite emoji as image glyphs that are sometimes not
 * repainted correctly after a color-to-transparent-to-color round-trip.
 *
 * Solution: pin the button children to the app's base text color via
 * `--text-foreground` (a CSS custom property that is independent of the
 * `color: transparent` set on ancestors), and transition the rows in/out via
 * `opacity` instead of `color`. This way the emoji in action labels is never
 * made transparent and the rendering bug cannot occur.
 */

/* 1. Override color: transparent on button children during both enter-from and leave-to */
.fade-text-enter-from .actions-row,
.fade-text-enter-from .actions-row *,
.fade-text-enter-from .prompts-row,
.fade-text-enter-from .prompts-row *,
.fade-text-leave-to .actions-row,
.fade-text-leave-to .actions-row *,
.fade-text-leave-to .prompts-row,
.fade-text-leave-to .prompts-row * {
  color: var(--text-foreground) !important;
}

/* 2. Action/prompt rows start invisible on enter, end invisible on leave;
 *    pointer-events disabled so invisible buttons cannot be accidentally tapped. */
.fade-text-enter-from .actions-row,
.fade-text-enter-from .prompts-row,
.fade-text-leave-to .actions-row,
.fade-text-leave-to .prompts-row {
  opacity: 0;
  pointer-events: none;
}

/* 3. Transition rows with opacity (not color) during active phases;
 *    children opt-out of the global color transition entirely. */
.fade-text-enter-active .actions-row,
.fade-text-enter-active .prompts-row,
.fade-text-leave-active .actions-row,
.fade-text-leave-active .prompts-row {
  transition: opacity 0.25s ease !important;
}
.fade-text-enter-active .actions-row *,
.fade-text-enter-active .prompts-row *,
.fade-text-leave-active .actions-row *,
.fade-text-leave-active .prompts-row * {
  transition: none !important;
}
</style>
