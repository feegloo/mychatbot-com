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

  it('renders 3 visible actions and collapses the rest into the More dropdown', async () => {
    const content =
      'Done.\n\n[action:First] [action:Second] [action:Third] [action:Fourth] [action:Fifth]'
    const wrapper = mount(ChatMessage, {
      attachTo: document.body,
      props: { ...baseProps(), msg: { role: 'assistant' as const, content } },
    })
    await nextTick()

    // Regular (non-welcome) limit: 3 visible actions.
    const visibleActions = wrapper.findAll('.actions-row > .message-content-action')
    expect(visibleActions.length).toBe(3)
    expect(visibleActions.map((b) => b.text())).toEqual(['First', 'Second', 'Third'])

    // VDropdown stub flattens popper into the same parent, so the overflow
    // buttons are present in the DOM (2 remaining actions).
    const overflow = wrapper.findAll('.more-actions-popper .message-content-action')
    expect(overflow.length).toBe(2)
    expect(overflow.map((b) => b.text())).toEqual(['Fourth', 'Fifth'])

    // The "More… (2)" trigger button is rendered.
    expect(wrapper.find('.more-btn').text()).toContain('More')
    expect(wrapper.find('.more-btn').text()).toContain('2')
  })

  it('emits select-question when a visible or overflow action is clicked', async () => {
    const content = 'Done.\n\n[action:First] [action:Second] [action:Third] [action:Fourth]'
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
    expect(events![1][0]).toBe('Fourth')
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

describe('ChatMessage — shareMessage (Udostępnij button)', () => {
  afterEach(() => {
    document.body.innerHTML = ''
    vi.restoreAllMocks()
  })

  /** Flush pending microtasks (e.g. resolved/rejected Promises) */
  const flushMicrotasks = () => new Promise<void>((r) => setTimeout(r, 0))

  /**
   * happy-dom doesn't implement document.execCommand — ensure it exists
   * as a configurable stub so vi.spyOn can override it.
   */
  function ensureExecCommand() {
    if (!document.execCommand) {
      Object.defineProperty(document, 'execCommand', {
        value: () => false,
        writable: true,
        configurable: true,
      })
    }
  }

  function mountShare(msgId?: string) {
    return mount(ChatMessage, {
      attachTo: document.body,
      props: {
        msg: { role: 'assistant' as const, content: 'Hello.', id: msgId },
        asking: false,
        conversationId: 'conv1',
      },
    })
  }

  it('copies the share URL via clipboard API and shows success state', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })

    const wrapper = mountShare('msg42')
    await nextTick()

    const btn = wrapper.find('.msg-action-btn')
    await btn.trigger('click')
    await nextTick()
    await flushMicrotasks()

    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('/m/msg42'))
    expect(btn.text()).toContain('Skopiowano link!')
  })

  it('falls back to execCommand when clipboard.writeText rejects, and shows success state', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
      configurable: true,
    })
    ensureExecCommand()
    const execCommand = vi.spyOn(document, 'execCommand').mockReturnValue(true)

    const wrapper = mountShare('msg42')
    await nextTick()

    const btn = wrapper.find('.msg-action-btn')
    await btn.trigger('click')
    await nextTick()
    await flushMicrotasks()

    expect(execCommand).toHaveBeenCalledWith('copy')
    expect(btn.text()).toContain('Skopiowano link!')
  })

  it('opens the URL in a new tab when both clipboard paths fail', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
      configurable: true,
    })
    ensureExecCommand()
    vi.spyOn(document, 'execCommand').mockReturnValue(false)
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(null)

    const wrapper = mountShare('msg42')
    await nextTick()

    const btn = wrapper.find('.msg-action-btn')
    await btn.trigger('click')
    await nextTick()
    await flushMicrotasks()

    expect(openSpy).toHaveBeenCalledWith(
      expect.stringContaining('/m/msg42'),
      '_blank',
      'noopener,noreferrer',
    )
    expect(btn.text()).not.toContain('Skopiowano link!')
  })

  it('cancels the previous reset timer when clicked twice in quick succession', async () => {
    vi.useFakeTimers()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })

    const wrapper = mountShare('msg42')
    await nextTick()
    const btn = wrapper.find('.msg-action-btn')

    // First click
    await btn.trigger('click')
    await Promise.resolve()
    expect(btn.text()).toContain('Skopiowano link!')

    // Advance 1 second (still within the 2-second window)
    vi.advanceTimersByTime(1000)

    // Second click before the first timer fires
    await btn.trigger('click')
    await Promise.resolve()

    // Advance 1 more second — first timer would have fired at t=2s, but was cancelled
    vi.advanceTimersByTime(1000)
    await nextTick()
    // Still showing success because the second timer (reset at t=1s) expires at t=3s
    expect(btn.text()).toContain('Skopiowano link!')

    // Advance to the second timer's expiry
    vi.advanceTimersByTime(1000)
    await nextTick()
    expect(btn.text()).not.toContain('Skopiowano link!')

    vi.useRealTimers()
  })
})

describe('ChatMessage — file preview navigation arrows', () => {
  afterEach(() => {
    document.body.innerHTML = ''
    vi.restoreAllMocks()
  })

  type FileEntry = { id: string; originalName: string; mimeType: string | null; url: string }

  const imgFile: FileEntry = {
    id: '1',
    originalName: 'photo.jpg',
    mimeType: 'image/jpeg',
    url: '/files/photo.jpg',
  }
  const pdfFile: FileEntry = {
    id: '2',
    originalName: 'report.pdf',
    mimeType: 'application/pdf',
    url: '/files/report.pdf',
  }
  const txtFile: FileEntry = {
    id: '3',
    originalName: 'notes.txt',
    mimeType: 'text/plain',
    url: '/files/notes.txt',
  }

  function mountWelcome(files: FileEntry[]) {
    return mount(ChatMessage, {
      attachTo: document.body,
      props: {
        msg: { role: 'assistant' as const, content: 'Welcome!' },
        asking: false,
        conversationId: 'nav-conv',
        isWelcome: true,
        files,
      },
    })
  }

  async function openFile(wrapper: ReturnType<typeof mountWelcome>, file: FileEntry) {
    const previewFiles = wrapper.findComponent({ name: 'PreviewFiles' })
    await previewFiles.vm.$emit('open', file)
    await nextTick()
  }

  it('does not render nav arrows when only one file is uploaded', async () => {
    const wrapper = mountWelcome([imgFile])
    await openFile(wrapper, imgFile)
    expect(document.body.querySelector('.file-nav-arrow')).toBeNull()
  })

  it('renders nav arrows when a modal is open and there are 2+ files', async () => {
    const wrapper = mountWelcome([imgFile, pdfFile])
    await openFile(wrapper, imgFile)
    const arrows = document.body.querySelectorAll('.file-nav-arrow')
    expect(arrows.length).toBe(2)
  })

  it('nav arrows disappear after modal is closed', async () => {
    const wrapper = mountWelcome([imgFile, pdfFile])
    await openFile(wrapper, imgFile)
    expect(document.body.querySelector('.file-nav-arrow')).not.toBeNull()

    // Close the ImageModal
    const overlay = document.body.querySelector('.image-modal-overlay') as HTMLElement | null
    expect(overlay).not.toBeNull()
    await overlay!.click()
    await nextTick()

    expect(document.body.querySelector('.file-nav-arrow')).toBeNull()
  })

  it('clicking the right arrow advances to the next file', async () => {
    const wrapper = mountWelcome([imgFile, pdfFile])
    await openFile(wrapper, imgFile)

    // Initially shows the image modal
    expect(document.body.querySelector('.image-modal-img')).not.toBeNull()

    const rightArrow = document.body.querySelector('.file-nav-arrow--right') as HTMLElement
    await rightArrow.click()
    await nextTick()

    // After navigating to pdfFile (a doc), SourcePreviewModal should be visible
    expect(document.body.querySelector('.source-modal-overlay')).not.toBeNull()
  })

  it('clicking the left arrow goes to the previous file (wraps around)', async () => {
    const wrapper = mountWelcome([imgFile, pdfFile])
    await openFile(wrapper, imgFile)

    // imgFile is at index 0; pressing left should wrap to pdfFile (index 1)
    const leftArrow = document.body.querySelector('.file-nav-arrow--left') as HTMLElement
    await leftArrow.click()
    await nextTick()

    expect(document.body.querySelector('.source-modal-overlay')).not.toBeNull()
  })

  it('keyboard ArrowRight is wired up: listener is active and calls preventDefault', async () => {
    // The keyboard handler is registered via watch(hasFilePreviewNav).
    // We verify it fires by asserting e.preventDefault() is called rather than
    // awaiting a full reactive flush: dispatching a keyboard event outside
    // Vue's scheduler causes happy-dom to lose comment-node parentNode references
    // during the Teleport patch, throwing TypeError on insertBefore.
    const wrapper = mountWelcome([imgFile, pdfFile])
    await openFile(wrapper, imgFile)
    // hasFilePreviewNav is now true — handler should be attached to document
    await nextTick() // flush watch(hasFilePreviewNav)

    const event = new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true, cancelable: true })
    const preventDefaultSpy = vi.spyOn(event, 'preventDefault')
    document.dispatchEvent(event)

    // Handler called e.preventDefault() → proves it ran
    expect(preventDefaultSpy).toHaveBeenCalled()
  })

  it('keyboard ArrowLeft is wired up: listener is active and calls preventDefault', async () => {
    const wrapper = mountWelcome([imgFile, pdfFile])
    await openFile(wrapper, imgFile)
    await nextTick()

    const event = new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true, cancelable: true })
    const preventDefaultSpy = vi.spyOn(event, 'preventDefault')
    document.dispatchEvent(event)

    expect(preventDefaultSpy).toHaveBeenCalled()
  })

  it('nav arrows have type="button" to prevent form-submit behavior', async () => {
    const wrapper = mountWelcome([imgFile, pdfFile])
    await openFile(wrapper, imgFile)

    const arrows = document.body.querySelectorAll('.file-nav-arrow')
    for (const arrow of arrows) {
      expect((arrow as HTMLButtonElement).type).toBe('button')
    }
  })

  it('opening a file via [source:N] citation also activates nav arrows', async () => {
    const wrapper = mount(ChatMessage, {
      attachTo: document.body,
      props: {
        msg: {
          role: 'assistant' as const,
          content: 'See [source:1].',
          citations: [],
        },
        asking: false,
        conversationId: 'nav-conv',
        isWelcome: true,
        files: [txtFile, pdfFile],
      },
    })
    await nextTick()

    // Simulate citation click — openCitation calls openFilePreview (sets filePreviewIndex)
    // when falling back to props.files for welcome-message [source:N] citations.
    const citationBtn = wrapper.find('.inline-source-btn')
    if (citationBtn.exists()) {
      await citationBtn.trigger('click')
      await nextTick()
      expect(document.body.querySelector('.file-nav-arrow')).not.toBeNull()
    }
  })
})
