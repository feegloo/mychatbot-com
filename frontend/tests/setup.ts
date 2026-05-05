/**
 * Global setup for Vitest unit tests.
 *
 * floating-vue's VDropdown relies on layout measurement APIs that
 * happy-dom doesn't implement fully (``ResizeObserver``, ``getClientRects``
 * shape), so the real component throws during ``mounted`` — which masks
 * the actual assertions. Tests only care that the trigger and the popper
 * slot content both render in the DOM, so we ship a tiny stub that does
 * exactly that: default slot as the trigger, ``popper`` named slot as
 * the menu body, flattened into a plain ``<div>`` tree.
 */
import { Fragment, h, defineComponent } from 'vue'
import { vi } from 'vitest'
import { config } from '@vue/test-utils'
import { appReady } from '../src/composables/appReady'

// Opt out of the ``appReady`` hysteresis (two requestAnimationFrames on
// first paint) in unit tests — the flip-to-true mid-test interacts with
// Vue's TextFade <Transition> and can clobber imperative DOM mutations
// (e.g. ChatMessage's action-button overflow collapsing).
appReady.value = true

// TextFade is imported directly by SFCs (so ``global.stubs`` doesn't
// apply).  Replace it module-wide with a transparent passthrough so
// imperative DOM edits made after mount survive Vue's <Transition>
// appear/leave cycles during tests.
vi.mock('../src/components/TextFade.vue', () => ({
  default: defineComponent({
    name: 'TextFadeStub',
    props: ['trigger'],
    setup(_props, { slots }) {
      return () => h(Fragment, null, [slots.default?.()])
    },
  }),
}))

// UDocViewer pulls in @docmentis/udoc-viewer whose internal module
// `@docmentis/udoc-viewer/dist/src/ui/framework/store` is absent in the test
// environment. Replace it with a transparent stub so SourcePreviewModal (and
// tests that open it) can load and render correctly.
vi.mock('../src/components/UDocViewer.vue', () => ({
  default: defineComponent({ name: 'UDocViewerStub', template: '<div class="udoc-viewer-stub" />' }),
}))

/**
 * Spy that tests can import to assert the dropdown was asked to close
 * (the real ChatMessage calls ``welcomeMoreDropdown.value?.hide()``
 * from its Escape handler).  Reset between tests via
 * ``vDropdownHideSpy.mockClear()``.
 */
export const vDropdownHideSpy = vi.fn()

config.global.stubs = {
  ...(config.global.stubs ?? {}),
  VDropdown: {
    name: 'VDropdownStub',
    setup(_props, { slots, expose }) {
      expose({ hide: vDropdownHideSpy, show: () => {} })
      // Fragment root so the trigger stays a direct child of its parent
      // (e.g. ``.welcome-suggested-questions > .question-pill`` selectors).
      return () => h(Fragment, null, [slots.default?.(), slots.popper?.({ hide: vDropdownHideSpy })])
    },
  },
  // Stub built-in Transition to a transparent passthrough. The real Transition
  // uses comment nodes as anchors which lose their parentNode reference in
  // happy-dom when reactive updates are triggered outside Vue's scheduler
  // (e.g. keyboard event handlers registered on document).
  Transition: { template: '<slot />' },
}

