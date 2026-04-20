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
  expect(wrap1.findAll('.action-more-wrap > .action-btn[data-action]').length).toBe(3)
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
})
