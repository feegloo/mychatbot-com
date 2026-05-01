import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// Track how many times a PDF document is fetched so we can assert that
// changing the url prop re-triggers loadPdf().
const getDocumentMock = vi.fn()
const destroyMock = vi.fn()

vi.mock('pdfjs-dist', () => {
  return {
    GlobalWorkerOptions: { workerSrc: '' },
    TextLayer: class {
      async render() {
        /* noop */
      }
    },
    getDocument: (...args: unknown[]) => getDocumentMock(...args),
  }
})

beforeEach(() => {
  getDocumentMock.mockReset()
  destroyMock.mockReset()
  // jsdom doesn't implement scrollIntoView, which the viewer calls on page navigation.
  if (!(Element.prototype as unknown as { scrollIntoView?: unknown }).scrollIntoView) {
    Element.prototype.scrollIntoView = function scrollIntoView() {
      /* noop */
    }
  }
  getDocumentMock.mockImplementation(() => ({
    promise: Promise.resolve({
      numPages: 3,
      getPage: () =>
        Promise.resolve({
          getViewport: () => ({ width: 600, height: 800, scale: 1 }),
          render: () => ({ promise: Promise.resolve() }),
          getTextContent: () => Promise.resolve({ items: [] }),
        }),
      destroy: destroyMock,
    }),
  }))
})

describe('PdfPageViewer reacts to prop changes', () => {
  it('reloads the PDF when the url prop changes (e.g. clicking a different citation)', async () => {
    const PdfPageViewer = (await import('../../src/components/PdfPageViewer.vue')).default

    const wrapper = mount(PdfPageViewer, {
      props: { url: '/api/storage/abc/first.pdf', page: 1, highlightText: '' },
      attachTo: document.body,
    })

    // Wait for loadPdf()'s async chain (getDocument → render) to settle
    await flushPromises()

    expect(getDocumentMock).toHaveBeenCalledTimes(1)
    expect(getDocumentMock.mock.calls[0][0].url).toBe('/api/storage/abc/first.pdf')

    // Simulate the source preview modal swapping in a different citation
    await wrapper.setProps({ url: '/api/storage/abc/second.pdf', page: 2 })
    await flushPromises()

    expect(getDocumentMock).toHaveBeenCalledTimes(2)
    expect(getDocumentMock.mock.calls[1][0].url).toBe('/api/storage/abc/second.pdf')

    wrapper.unmount()
  })

  it('does not reload the PDF when only the page prop changes', async () => {
    const PdfPageViewer = (await import('../../src/components/PdfPageViewer.vue')).default

    const wrapper = mount(PdfPageViewer, {
      props: { url: '/api/storage/abc/first.pdf', page: 1, highlightText: '' },
      attachTo: document.body,
    })

    await flushPromises()

    expect(getDocumentMock).toHaveBeenCalledTimes(1)

    await wrapper.setProps({ page: 2 })
    await flushPromises()

    // Same document, no extra fetch
    expect(getDocumentMock).toHaveBeenCalledTimes(1)

    wrapper.unmount()
  })
})

describe('PdfPageViewer toolbar optional controls', () => {
  async function mountViewer(props: Record<string, unknown> = {}) {
    const PdfPageViewer = (await import('../../src/components/PdfPageViewer.vue')).default
    return mount(PdfPageViewer, {
      props: { url: '/api/storage/abc/doc.pdf', page: 1, ...props },
      attachTo: document.body,
    })
  }

  it('hides "Open PDF" button and its divider by default', async () => {
    const wrapper = await mountViewer()
    await flushPromises()

    expect(wrapper.find('button.pdf-tool-btn--text').exists()).toBe(false)
    wrapper.unmount()
  })

  it('shows "Open PDF" button when showOpenPdf is true', async () => {
    const wrapper = await mountViewer({ showOpenPdf: true })
    await flushPromises()

    const openBtn = wrapper.find('button.pdf-tool-btn--text')
    expect(openBtn.exists()).toBe(true)
    expect(openBtn.text()).toBe('Open PDF')
    wrapper.unmount()
  })

  it('emits "openPdf" when "Open PDF" button is clicked', async () => {
    const wrapper = await mountViewer({ showOpenPdf: true })
    await flushPromises()

    await wrapper.find('button.pdf-tool-btn--text').trigger('click')

    expect(wrapper.emitted('openPdf')).toBeTruthy()
    expect(wrapper.emitted('openPdf')!.length).toBe(1)
    wrapper.unmount()
  })

  it('hides close button by default', async () => {
    const wrapper = await mountViewer()
    await flushPromises()

    const closeBtn = wrapper.find('button[aria-label="Close"]')
    expect(closeBtn.exists()).toBe(false)
    wrapper.unmount()
  })

  it('shows close button when showClose is true', async () => {
    const wrapper = await mountViewer({ showClose: true })
    await flushPromises()

    expect(wrapper.find('button[aria-label="Close"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('emits "close" when close button is clicked', async () => {
    const wrapper = await mountViewer({ showClose: true })
    await flushPromises()

    await wrapper.find('button[aria-label="Close"]').trigger('click')

    expect(wrapper.emitted('close')).toBeTruthy()
    expect(wrapper.emitted('close')!.length).toBe(1)
    wrapper.unmount()
  })

  it('prev and next buttons have accessible aria-labels', async () => {
    const wrapper = await mountViewer()
    await flushPromises()

    const prev = wrapper.find('button[aria-label="Previous page"]')
    const next = wrapper.find('button[aria-label="Next page"]')
    expect(prev.exists()).toBe(true)
    expect(next.exists()).toBe(true)
    wrapper.unmount()
  })
})
