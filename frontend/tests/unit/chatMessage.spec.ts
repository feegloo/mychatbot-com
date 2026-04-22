import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ChatMessage from '../../src/components/ChatMessage.vue'

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
  })

  it('renders the first 5 welcome prompts inline and moves the rest to More preserving order', async () => {
    const wrapper = mount(ChatMessage, {
      attachTo: document.body,
      props: {
        ...baseProps(),
        isWelcome: true,
        suggestedQuestions: [
          'Text 1',
          'Action 1 🧠',
          'Text 2',
          'Action 2 📓',
          'Action 3 🧩',
          'Text 3',
        ],
      },
    })

    const visibleQuestionPills = wrapper.findAll('.welcome-suggested-questions > .question-pill')
    expect(visibleQuestionPills.some((p) => p.text().includes('More ...'))).toBe(true)
    expect(wrapper.text()).toContain('Text 1')
    expect(wrapper.text()).toContain('Action 1')
    expect(wrapper.text()).toContain('Text 2')
    expect(wrapper.text()).toContain('Action 2')
    expect(wrapper.text()).toContain('Action 3')
    expect(wrapper.text()).not.toContain('Text 3')

    await wrapper.find('.welcome-more-wrap').trigger('click')
    expect(wrapper.text()).toContain('Action 1')
    expect(wrapper.text()).toContain('Text 2')
    expect(wrapper.text()).toContain('Action 2')
    expect(wrapper.text()).toContain('Action 3')
    expect(wrapper.text()).toContain('Text 3')

    document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await nextTick()
    expect(wrapper.find('.welcome-more-menu').exists()).toBe(false)
  })

  it('closes welcome More menu with Escape from a menu item', async () => {
    const wrapper = mount(ChatMessage, {
      attachTo: document.body,
      props: {
        ...baseProps(),
        isWelcome: true,
        suggestedQuestions: [
          'Text 1',
          'Text 2',
          'Text 3',
          'Action 1 🧠',
          'Action 2 📓',
          'Action 3 🧩',
        ],
      },
    })

    await wrapper.find('.welcome-more-wrap').trigger('click')
    const menuItem = wrapper.find('.welcome-more-item')
    expect(menuItem.exists()).toBe(true)

    await menuItem.trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('.welcome-more-menu').exists()).toBe(false)
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
      expect(wrapper.findAll('.action-visible-row > .action-btn[data-action]').length).toBe(3)
      expect(wrapper.findAll('.action-more-menu .action-btn[data-action]').length).toBe(2)
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

      vi.runAllTimers()
      await nextTick()

      expect(wrap1.find('.action-more-btn').exists()).toBe(true)
  expect(wrap1.findAll('.action-visible-row > .action-btn[data-action]').length).toBe(3)
  expect(wrap1.findAll('.action-more-menu .action-btn[data-action]').length).toBe(2)

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
