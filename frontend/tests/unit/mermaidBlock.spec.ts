import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import MermaidBlock from '../../src/components/MermaidBlock.vue'

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(async () => ({
      svg: '<svg xmlns="http://www.w3.org/2000/svg"><g /></svg>',
    })),
  },
}))

describe('MermaidBlock drag panning', () => {
  it('pans diagram via pointer drag', async () => {
    const wrapper = mount(MermaidBlock, {
      props: {
        code: 'graph TD; A-->B;',
      },
    })

    await Promise.resolve()
    await new Promise((resolve) => requestAnimationFrame(resolve))

    const setupState = (wrapper.vm as unknown as {
      $: {
        setupState: {
          onPointerDown: (event: unknown) => void
          onPointerMove: (event: unknown) => void
          onPointerUp: (event: unknown) => void
          ready: boolean
          mode: 'diagram' | 'text'
        }
      }
    }).$.setupState
    setupState.ready = true
    const currentTarget = {
      setPointerCapture: vi.fn(),
      releasePointerCapture: vi.fn(),
    } as unknown as EventTarget
    const target = {
      closest: vi.fn(() => null),
    } as unknown as EventTarget

    setupState.onPointerDown({
      pointerId: 10,
      pointerType: 'mouse',
      button: 0,
      clientX: 100,
      clientY: 100,
      target,
      currentTarget,
      preventDefault: vi.fn(),
    })
    setupState.onPointerMove({
      pointerId: 10,
      clientX: 140,
      clientY: 130,
      target,
      currentTarget,
      preventDefault: vi.fn(),
    })
    setupState.onPointerUp({
      pointerId: 10,
      currentTarget,
    })
    await nextTick()

    const style = wrapper.find('.mermaid-svg-wrapper').attributes('style')
    expect(style).toContain('translate(40px, 30px)')
  })
})
