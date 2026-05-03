import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ChatMessage from '../../src/components/ChatMessage.vue'
import { vDropdownHideSpy } from '../setup'

vi.mock('../../src/api', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>
  return { ...actual, getStorageUrl: (_cid: string, name: string) => `/files/${name}` }
})

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
    const overflow = wrapper.findAll('.more-actions-popper .message-content-action')
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
    await wrapper.find('.more-actions-popper .message-content-action').trigger('click')

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
    expect(wrapper.findAll('.more-actions-popper .message-content-action').length).toBe(2)
  })

  it('shows 5 actions visible on welcome messages with no prompts (image uploads)', async () => {
    const content =
      'Welcome!\n\n' +
      '[action:A1] [action:A2] [action:A3] [action:A4] [action:A5] [action:A6] [action:A7]'
    const wrapper = mount(ChatMessage, {
      attachTo: document.body,
      props: {
        ...baseProps(),
        isWelcome: true,
        msg: { role: 'assistant' as const, content },
      },
    })
    await nextTick()

    expect(wrapper.findAll('.prompts-row > button').length).toBe(0)
    expect(wrapper.findAll('.actions-row > .message-content-action').length).toBe(5)
    expect(wrapper.findAll('.more-actions-popper .message-content-action').length).toBe(2)
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

describe('ChatMessage — image citations deduplication', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  function makeMsg(id: string, imageNames: string[]) {
    return {
      id,
      role: 'assistant' as const,
      content: 'Answer.',
      citations: imageNames.map((name, idx) => ({
        fileName: 'doc.pdf',
        chunkId: `c${idx}`,
        text: 'chunk',
        section: `Image (page ${idx + 1})`,
        page: idx + 1,
        imageName: name,
      })),
    }
  }

  it('shows all images when there are no previous messages', async () => {
    const msg = makeMsg('m1', ['img1.png', 'img2.png'])
    const wrapper = mount(ChatMessage, {
      attachTo: document.body,
      props: { ...baseProps(), msg, allMessages: [msg] },
    })
    await nextTick()
    expect(wrapper.findAll('.citation-image-thumb').length).toBe(2)
  })

  it('hides images already shown in an earlier message', async () => {
    const prev = makeMsg('m1', ['img1.png', 'img2.png'])
    const curr = makeMsg('m2', ['img1.png', 'img3.png'])
    const allMessages = [prev, curr]

    const wrapper = mount(ChatMessage, {
      attachTo: document.body,
      props: { ...baseProps(), msg: curr, allMessages },
    })
    await nextTick()

    // img1.png was in prev — only img3.png should be shown
    const thumbs = wrapper.findAll('.citation-image-thumb')
    expect(thumbs.length).toBe(1)
    expect(thumbs[0].find('.citation-image-label').text()).toContain('Image (page 2)')
  })

  it('shows no thumbnails when all images appeared in earlier messages', async () => {
    const prev = makeMsg('m1', ['img1.png', 'img2.png'])
    const curr = makeMsg('m2', ['img1.png', 'img2.png'])

    const wrapper = mount(ChatMessage, {
      attachTo: document.body,
      props: { ...baseProps(), msg: curr, allMessages: [prev, curr] },
    })
    await nextTick()
    expect(wrapper.findAll('.citation-image-thumb').length).toBe(0)
  })
})

describe('ChatMessage — openFilePreview SVG stretch', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  function welcomeProps(file: {
    id: string
    originalName: string
    mimeType: string | null
    url: string
  }) {
    return {
      msg: { role: 'assistant' as const, content: 'Welcome!' },
      asking: false,
      conversationId: 'abc123',
      isWelcome: true,
      files: [file],
    }
  }

  async function openFirstFile(file: {
    id: string
    originalName: string
    mimeType: string | null
    url: string
  }) {
    const wrapper = mount(ChatMessage, {
      attachTo: document.body,
      props: welcomeProps(file),
    })
    await nextTick()

    // Emit the `open` event on PreviewFiles to simulate a click
    const previewFiles = wrapper.findComponent({ name: 'PreviewFiles' })
    expect(previewFiles.exists()).toBe(true)
    await previewFiles.vm.$emit('open', file)
    await nextTick()

    return wrapper
  }

  it('opens ImageModal with stretch=true for SVG with image/svg+xml MIME type', async () => {
    await openFirstFile({
      id: '1',
      originalName: 'diagram.svg',
      mimeType: 'image/svg+xml',
      url: '/files/diagram.svg',
    })
    const img = document.body.querySelector('.image-modal-img')
    expect(img).not.toBeNull()
    expect(img!.classList.contains('image-modal-img--stretch')).toBe(true)
  })

  it('opens ImageModal with stretch=true for SVG with missing MIME type (extension fallback)', async () => {
    await openFirstFile({
      id: '2',
      originalName: 'diagram.svg',
      mimeType: null,
      url: '/files/diagram.svg',
    })
    const img = document.body.querySelector('.image-modal-img')
    expect(img).not.toBeNull()
    expect(img!.classList.contains('image-modal-img--stretch')).toBe(true)
  })

  it('opens ImageModal with stretch=true for SVG with incorrect MIME type (extension fallback)', async () => {
    await openFirstFile({
      id: '3',
      originalName: 'diagram.svg',
      mimeType: 'application/octet-stream',
      url: '/files/diagram.svg',
    })
    const img = document.body.querySelector('.image-modal-img')
    expect(img).not.toBeNull()
    expect(img!.classList.contains('image-modal-img--stretch')).toBe(true)
  })

  it('opens ImageModal without stretch for regular images', async () => {
    await openFirstFile({
      id: '4',
      originalName: 'photo.jpg',
      mimeType: 'image/jpeg',
      url: '/files/photo.jpg',
    })
    const img = document.body.querySelector('.image-modal-img')
    expect(img).not.toBeNull()
    expect(img!.classList.contains('image-modal-img--stretch')).toBe(false)
  })
})

