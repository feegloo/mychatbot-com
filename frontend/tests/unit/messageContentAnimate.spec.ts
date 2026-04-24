import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import MessageContent from '../../src/components/chat/MessageContent.vue'

describe('MessageContent – animate prop', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('applies word-reveal spans and emits "animated" on mount when animate=true', async () => {
    const wrapper = mount(MessageContent, {
      attachTo: document.body,
      props: { content: 'Hello beautiful world', animate: true },
    })
    await nextTick()

    // applyWordReveal wraps each word in a .word-reveal span
    const spans = wrapper.findAll('.word-reveal')
    expect(spans.length).toBe(3)

    // Emits exactly once
    const events = wrapper.emitted('animated')
    expect(events).toBeDefined()
    expect(events!.length).toBe(1)
  })

  it('does not apply word-reveal spans or emit "animated" when animate=false', async () => {
    const wrapper = mount(MessageContent, {
      attachTo: document.body,
      props: { content: 'Hello beautiful world', animate: false },
    })
    await nextTick()

    expect(wrapper.findAll('.word-reveal').length).toBe(0)
    expect(wrapper.emitted('animated')).toBeUndefined()
  })

  it('does not apply word-reveal spans when animate is omitted (defaults false)', async () => {
    const wrapper = mount(MessageContent, {
      attachTo: document.body,
      props: { content: 'Hello beautiful world' },
    })
    await nextTick()

    expect(wrapper.findAll('.word-reveal').length).toBe(0)
    expect(wrapper.emitted('animated')).toBeUndefined()
  })

  it('only animates on the first mount — re-mount with animate=false skips animation', async () => {
    // Simulate translation re-mount: first mount with animate=true (new message)
    const first = mount(MessageContent, {
      attachTo: document.body,
      props: { content: 'Hi there', animate: true },
    })
    await nextTick()
    expect(first.emitted('animated')!.length).toBe(1)
    first.unmount()

    // Second mount with animate=false (parent cleared the flag after animated event)
    const second = mount(MessageContent, {
      attachTo: document.body,
      props: { content: 'Translated: Hi there', animate: false },
    })
    await nextTick()
    expect(second.findAll('.word-reveal').length).toBe(0)
    expect(second.emitted('animated')).toBeUndefined()
  })
})
