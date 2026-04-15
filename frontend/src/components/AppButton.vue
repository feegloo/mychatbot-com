<template>
  <button class="app-btn" v-bind="$attrs">
    <slot />
  </button>
</template>

<script setup lang="ts">
/**
 * AppButton — mobile-safe button component.
 *
 * Fixes the iOS/Android double-tap issue where the first tap only applies
 * the CSS :hover state and the second tap actually fires the click event.
 *
 * How it works:
 *  • `touch-action: manipulation` disables double-tap-to-zoom so the
 *    browser fires the click immediately on the first tap.
 *  • All :hover styles are gated behind `@media (hover: hover)` so
 *    touch devices never enter a "sticky hover" state.
 *  • An :active style provides instant press feedback on touch.
 */
defineOptions({ inheritAttrs: true })
</script>

<style scoped>
.app-btn {
  /* Prevent double-tap-to-zoom so click fires on first tap */
  touch-action: manipulation;
  /* Remove the grey highlight rectangle on iOS/Android */
  -webkit-tap-highlight-color: transparent;
}

/* Hover effect only on devices with a real pointer (mouse / trackpad) */
@media (hover: hover) {
  .app-btn:hover:not(:disabled) {
    filter: brightness(1.15);
  }
}

/* Instant press feedback for touch and mouse */
.app-btn:active:not(:disabled) {
  filter: brightness(0.92);
}
</style>
