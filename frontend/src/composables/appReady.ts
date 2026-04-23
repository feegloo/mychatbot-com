import { ref } from 'vue'

/**
 * True once the initial page paint has settled. `TextFade` reads this to
 * suppress the appear animation on first load (so restored conversation
 * history renders instantly) while still animating subsequent mounts
 * triggered by new messages, translations, or any other text swap.
 *
 * A single shared ref is cheaper than per-component watchers and avoids
 * proliferating reactive subscriptions across every rendered text block.
 */
export const appReady = ref(false)

if (typeof window !== 'undefined') {
  // Two rAFs ensure the first paint has committed before we enable
  // animations — otherwise messages that mount in the same tick as the
  // route change would still animate in.
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      appReady.value = true
    })
  })
}
