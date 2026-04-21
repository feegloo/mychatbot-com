import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import MermaidBlock from '../../src/components/MermaidBlock.vue'

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(async () => ({
      svg: '<svg xmlns="http://www.w3.org/2000/svg"><g /></svg>',
    })),
  },
}))

type SetupState = {
  onPointerDown: (event: PointerEventLike) => void
  onPointerMove: (event: PointerEventLike) => void
  onPointerUp: (event: Pick<PointerEventLike, 'pointerId' | 'currentTarget'>) => void
  ready: boolean
}

type PointerEventLike = {
  pointerId: number
  pointerType?: string
  button?: number
  clientX: number
  clientY: number
  target: HTMLElement
  currentTarget: HTMLElement
  preventDefault: () => void
}

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
      $: { setupState: SetupState }
    }).$.setupState
    setupState.ready = true
    const currentTarget = document.createElement('div')
    const target = document.createElement('div')
    target.closest = vi.fn(() => null)

    const preventDefault = vi.fn()
    const setPointerCapture = vi.fn()
    const releasePointerCapture = vi.fn()
    currentTarget.setPointerCapture = setPointerCapture
    currentTarget.releasePointerCapture = releasePointerCapture

    setupState.onPointerDown({
      pointerId: 10,
      pointerType: 'mouse',
      button: 0,
      clientX: 100,
      clientY: 100,
      target,
      currentTarget,
      preventDefault,
    })
    setupState.onPointerMove({
      pointerId: 10,
      clientX: 140,
      clientY: 130,
      target,
      currentTarget,
      preventDefault,
    })
    setupState.onPointerUp({
      pointerId: 10,
      currentTarget,
    })
    await Promise.resolve()

    const style = wrapper.find('.mermaid-svg-wrapper').attributes('style')
    expect(style).toContain('translate(40px, 30px)')
    expect(preventDefault).toHaveBeenCalled()
    expect(setPointerCapture).toHaveBeenCalledWith(10)
    expect(releasePointerCapture).toHaveBeenCalledWith(10)
  })
})
