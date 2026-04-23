import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ChatMessage from '../../src/components/ChatMessage.vue'
import { vDropdownHideSpy } from '../setup'

function baseProps() {
  return {
    msg: {
      role: 'assistant' as const,
      content: 'Hello there.',
    },
    asking: false,
    conversationId: 'abc123',
  }
}

describe('ChatMessage suggested prompt overflow', () => {
  afterEach(() => {
    document.body.innerHTML = ''
    vDropdownHideSpy.mockClear()
  })

  it('still shows More after streaming completes (was prematurely locked with few buttons)', async () => {
    vi.useFakeTimers()
    try {
      const fewActions = 'Streaming...\n\n[action:First] [action:Second]'
      const manyActions =
        'Done.\n\n[action:First] [action:Second] [action:Third] [action:Fourth] [action:Fifth]'

      const wrapper = mount(ChatMessage, {
        attachTo: document.body,
        props: {
          ...baseProps(),
          asking: true,
          msg: { role: 'assistant' as const, content: fewActions },
        },
      })

      // Simulate timer firing mid-stream with only 2 buttons — should NOT lock the row
      vi.runAllTimers()
      await nextTick()
      expect(wrapper.find('.action-more-btn').exists()).toBe(false)

      // Streaming finishes — full content arrives, asking = false
      await wrapper.setProps({
        asking: false,
        msg: { role: 'assistant' as const, content: manyActions },
      })
      vi.runAllTimers()
      await nextTick()

      expect(wrapper.find('.action-more-btn').exists()).toBe(true)
      expect(wrapper.findAll('.action-visible-row > .action-btn[data-action]').length).toBe(2)
      expect(wrapper.findAll('.action-more-menu .action-btn[data-action]').length).toBe(3)
    } finally {
      vi.useRealTimers()
    }
  })

  it('collapses multiple [action:] buttons and keeps outside-click behavior scoped per instance', async () => {
    vi.useFakeTimers()
    try {
      const messageWithActions =
        'Done.\n\n[action:First action] [action:Second action] [action:Third action] [action:Fourth action] [action:Fifth action]'
      const wrap1 = mount(ChatMessage, {
        attachTo: document.body,
        props: {
          ...baseProps(),
          msg: { role: 'assistant', content: messageWithActions },
        },
      })
      const wrap2 = mount(ChatMessage, {
        attachTo: document.body,
        props: {
          ...baseProps(),
          msg: { role: 'assistant', content: messageWithActions },
        },
      })

      // Two ticks + a flushed timer pass lets FadeText mount its v-html
      // content and then gives ``transformActionButtonGroups`` (scheduled
      // via setTimeout) a chance to rewrite the DOM.
      await nextTick()
      await nextTick()
      await vi.runAllTimersAsync()
      await nextTick()

      expect(wrap1.find('.action-more-btn').exists()).toBe(true)
  expect(wrap1.findAll('.action-visible-row > .action-btn[data-action]').length).toBe(2)
  expect(wrap1.findAll('.action-more-menu .action-btn[data-action]').length).toBe(3)

      await wrap1.find('.action-more-btn').trigger('click')
      expect(wrap1.find('.action-more-wrap').classes()).toContain('open')

      await wrap2.find('.action-more-btn').trigger('click')
      expect(wrap2.find('.action-more-wrap').classes()).toContain('open')
      expect(wrap1.find('.action-more-wrap').classes()).not.toContain('open')
    } finally {
      vi.useRealTimers()
    }
  })

  it('emits `image-revealed` only for images added after the initial mount pass', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = mount(ChatMessage, {
        attachTo: document.body,
        props: {
          ...baseProps(),
          msg: { role: 'assistant' as const, content: '![existing](https://example.com/a.png)' },
        },
      })

      // First pass: `trackContentImages` runs with initial-mount images; these
      // must NOT be flagged `animateIn`, so revealing them should not emit.
      vi.runAllTimers()
      await nextTick()

      const findImg = () => wrapper.element.querySelector('img') as HTMLImageElement | null
      const existing = findImg()
      expect(existing).not.toBeNull()
      expect(existing!.dataset.animateIn).toBeUndefined()

      Object.defineProperty(existing!, 'naturalWidth', { configurable: true, value: 100 })
      existing!.dispatchEvent(new Event('load'))
      await nextTick()
      expect(wrapper.emitted('image-revealed')).toBeUndefined()

      // Second pass: a new image arrives (e.g. post-generation); it SHOULD be
      // flagged dynamic and emit `image-revealed` with success=true on load.
      await wrapper.setProps({
        msg: { role: 'assistant' as const, content: '![generated](https://example.com/b.png)' },
      })
      vi.runAllTimers()
      await nextTick()

      const generated = findImg()
      expect(generated).not.toBeNull()
      expect(generated!.dataset.animateIn).toBe('true')

      Object.defineProperty(generated!, 'naturalWidth', { configurable: true, value: 200 })
      generated!.dispatchEvent(new Event('load'))
      await nextTick()

      const events = wrapper.emitted('image-revealed') as unknown[][] | undefined
      expect(events).toBeDefined()
      expect(events!.length).toBe(1)
      expect(events![0][0]).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })
})
