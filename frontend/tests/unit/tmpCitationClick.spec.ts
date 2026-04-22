import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ChatMessage from '../../src/components/ChatMessage.vue'

describe('citation click after image gen - live update scenario', () => {
  it('opens source preview modal after content is updated from empty state', async () => {
    vi.useFakeTimers()
    const msg: any = {
      role: 'assistant',
      content: '',
      generatingImage: true,
    }
    const wrapper = mount(ChatMessage, {
      attachTo: document.body,
      props: {
        msg,
        asking: true,
        conversationId: 'abc123',
      },
    })
    await nextTick()
    // Simulate response arriving
    msg.content = `![Wyjście bez wyjaśnień](/api/storage/abc/generated-xyz.png)\n\n<p class="image-caption">"Wyjście bez wyjaśnień" [1][2][3][4]</p>`
    msg.citations = [
      { fileName: 'minibook.pdf', chunkId: 'c1', text: 'Chunk 1', section: 'S1', page: 1 },
      { fileName: 'minibook.pdf', chunkId: 'c2', text: 'Chunk 2', section: 'S2', page: 2 },
      { fileName: 'minibook.pdf', chunkId: 'c3', text: 'Chunk 3', section: 'S3', page: 3 },
      { fileName: 'minibook.pdf', chunkId: 'c4', text: 'Chunk 4', section: 'S4', page: 4 },
    ]
    msg.id = 'msg1'
    await wrapper.setProps({ msg: { ...msg }, asking: false })
    await nextTick()
    vi.advanceTimersByTime(200)
    await nextTick()
    
    const btn = wrapper.find('.inline-source-btn[data-source-idx="1"]')
    console.log('btn exists?', btn.exists(), 'html:', wrapper.html().slice(0, 500))
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')
    await nextTick()
    const sourceOverlay = document.querySelector('.source-modal-overlay')
    const imageOverlay = document.querySelector('.image-modal-overlay')
    console.log('sourceOverlay?', !!sourceOverlay, 'imageOverlay?', !!imageOverlay)
    expect(imageOverlay).toBeNull()
    expect(sourceOverlay).not.toBeNull()
    wrapper.unmount()
    vi.useRealTimers()
  })
})
