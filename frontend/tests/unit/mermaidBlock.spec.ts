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

describe('MermaidBlock drag panning', () => {
  it('pans diagram via pointer drag', async () => {
    const wrapper = mount(MermaidBlock, {
      props: {
        code: 'graph TD; A-->B;',
      },
    })

    await Promise.resolve()
    await new Promise((resolve) => requestAnimationFrame(resolve))

    const diagram = wrapper.find('.mermaid-diagram')
    expect(diagram.exists()).toBe(true)

    await diagram.trigger('pointerdown', {
      pointerId: 10,
      pointerType: 'mouse',
      button: 0,
      clientX: 100,
      clientY: 100,
    })
    await diagram.trigger('pointermove', {
      pointerId: 10,
      clientX: 140,
      clientY: 130,
    })
    await diagram.trigger('pointerup', { pointerId: 10 })

    const style = wrapper.find('.mermaid-svg-wrapper').attributes('style')
    expect(style).toContain('translate(40px, 30px)')
  })
})
