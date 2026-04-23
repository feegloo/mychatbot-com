import { afterEach, describe, expect, it } from 'vitest'
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

describe('ChatMessage', () => {
  afterEach(() => {
    document.body.innerHTML = ''
    vDropdownHideSpy.mockClear()
  })

  it('renders 1 visible action and collapses the rest into the More dropdown', async () => {
    const content =
      'Done.\n\n[action:First] [action:Second] [action:Third] [action:Fourth] [action:Fifth]'
    const wrapper = mount(ChatMessage, {
      attachTo: document.body,
      props: { ...baseProps(), msg: { role: 'assistant' as const, content } },
    })
    await nextTick()

    // Regular (non-welcome) limit: 1 visible action.
    const visibleActions = wrapper.findAll('.actions-row > .message-content-action')
    expect(visibleActions.length).toBe(1)
    expect(visibleActions[0].text()).toBe('First')

    // VDropdown stub flattens popper into the same parent, so the overflow
    // buttons are present in the DOM (4 remaining actions).
    const overflow = wrapper.findAll('.more-menu .message-content-action')
    expect(overflow.length).toBe(4)
    expect(overflow.map((b) => b.text())).toEqual(['Second', 'Third', 'Fourth', 'Fifth'])

    // The "More… (4)" trigger button is rendered.
    expect(wrapper.find('.more-btn').text()).toContain('More')
    expect(wrapper.find('.more-btn').text()).toContain('4')
  })

  it('emits select-question when a visible or overflow action is clicked', async () => {
    const content = 'Done.\n\n[action:First] [action:Second] [action:Third]'
    const wrapper = mount(ChatMessage, {
      attachTo: document.body,
      props: { ...baseProps(), msg: { role: 'assistant' as const, content } },
    })
    await nextTick()

    await wrapper.find('.actions-row > .message-content-action').trigger('click')
    await wrapper.find('.more-menu .message-content-action').trigger('click')

    const events = wrapper.emitted('select-question') as string[][] | undefined
    expect(events).toBeDefined()
    expect(events!.length).toBe(2)
    expect(events![0][0]).toBe('First')
    expect(events![1][0]).toBe('Second')
  })

  it('uses welcome limits (3 prompts + 2 actions visible) for welcome messages', async () => {
    const content =
      'Welcome!\n\n' +
      '[prompt:P1] [prompt:P2] [prompt:P3] [prompt:P4]\n\n' +
      '[action:A1] [action:A2] [action:A3] [action:A4]'
    const wrapper = mount(ChatMessage, {
      attachTo: document.body,
      props: {
        ...baseProps(),
        isWelcome: true,
        msg: { role: 'assistant' as const, content },
      },
    })
    await nextTick()

    expect(wrapper.findAll('.prompts-row > button').length).toBe(3)
    expect(wrapper.findAll('.actions-row > .message-content-action').length).toBe(2)
    expect(wrapper.findAll('.more-menu .message-content-action').length).toBe(2)
  })

  it('opens the source preview modal when an inline citation button is clicked', async () => {
    const wrapper = mount(ChatMessage, {
      attachTo: document.body,
      props: {
        ...baseProps(),
        msg: {
          role: 'assistant' as const,
          content: 'See [source:1] for details.',
          citations: [
            {
              fileName: 'notes.txt',
              chunkId: 'c1',
              text: 'Cited text',
              section: 'Intro',
              page: 2,
            },
          ],
        },
      },
    })
    await nextTick()

    // renderMarkdown turns [source:1] into a `.inline-source-btn` button.
    const btn = wrapper.find('.inline-source-btn')
    expect(btn.exists()).toBe(true)

    await btn.trigger('click')
    await nextTick()

    // SourcePreviewModal teleports its body to document.body, so search there.
    expect(document.body.textContent).toContain('Cited text')
  })
})
