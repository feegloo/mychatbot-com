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
  switchToDiagram: () => void
  mode: 'diagram' | 'text'
  ready: boolean
  renderError: string | null
  renderedSvg: string
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

describe('MermaidBlock render failure handling', () => {
  it('stays in diagram mode and records error when render fails', async () => {
    const mermaid = (await import('mermaid')).default as unknown as {
      render: ReturnType<typeof vi.fn>
    }
    mermaid.render.mockRejectedValueOnce(new Error('bad syntax'))
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const wrapper = mount(MermaidBlock, {
      props: { code: 'graph TD; A-->B;' },
    })

    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => requestAnimationFrame(resolve))

    const state = (wrapper.vm as unknown as {
      $: { setupState: SetupState }
    }).$.setupState

    expect(state.mode).toBe('diagram')
    expect(state.renderError).toBe('bad syntax')
    expect(state.renderedSvg).toBe('')
    expect(consoleSpy).toHaveBeenCalled()

    consoleSpy.mockRestore()
    mermaid.render.mockResolvedValue({
      svg: '<svg xmlns="http://www.w3.org/2000/svg"><g /></svg>',
    })
  })

  it('re-renders when user toggles back to diagram after a failed render', async () => {
    const mermaid = (await import('mermaid')).default as unknown as {
      render: ReturnType<typeof vi.fn>
    }
    mermaid.render.mockRejectedValueOnce(new Error('bad syntax'))
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const wrapper = mount(MermaidBlock, {
      props: { code: 'graph TD; A-->B;' },
    })

    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => requestAnimationFrame(resolve))

    const state = (wrapper.vm as unknown as {
      $: { setupState: SetupState }
    }).$.setupState

    state.mode = 'text'
    mermaid.render.mockResolvedValueOnce({
      svg: '<svg xmlns="http://www.w3.org/2000/svg"><g class="retry" /></svg>',
    })

    state.switchToDiagram()
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => requestAnimationFrame(resolve))

    expect(state.mode).toBe('diagram')
    expect(state.renderError).toBeNull()
    expect(state.renderedSvg).toContain('retry')

    consoleSpy.mockRestore()
  })
})
