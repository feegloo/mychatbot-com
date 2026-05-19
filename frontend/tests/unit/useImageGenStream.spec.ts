import { afterEach, describe, expect, it, vi } from 'vitest'

const {
  announceImageMock,
  generateImageStreamMock,
  getStorageUrlMock,
} = vi.hoisted(() => ({
  announceImageMock: vi.fn(),
  generateImageStreamMock: vi.fn(),
  getStorageUrlMock: vi.fn(),
}))

vi.mock('../../src/api', () => ({
  announceImage: announceImageMock,
  generateImageStream: generateImageStreamMock,
  getStorageUrl: getStorageUrlMock,
}))

vi.mock('../../src/utils/fingerprint', () => ({
  getBrowserFingerprint: () => Promise.resolve('test-fingerprint-abc123'),
}))

import { runImageGenStream } from '../../src/composables/useImageGenStream'

describe('runImageGenStream', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('falls back to final generated image as a synthetic partial frame', async () => {
    vi.useFakeTimers()

    const reactiveMsg: {
      role: 'assistant'
      content: string
      generatingImage?: boolean
      imagePartialDataUrl?: string
      imagePartialIndex?: number
      imageDetailedPrompt?: string
      imageAnnouncement?: string
    } = {
      role: 'assistant',
      content: '',
    }

    announceImageMock.mockResolvedValue({ announcement: '' })
    getStorageUrlMock.mockReturnValue('https://example.local/final.png')

    generateImageStreamMock.mockImplementation(
      async (_conversationId: string, _question: string, _fingerprint: string | undefined, callbacks: {
        onComplete: (data: {
          answer: string
          citations: []
          generatedImage: { fileName: string; imagePrompt: string; revisedPrompt: string; imageTitle: string }
        }) => void
      }) => {
        callbacks.onComplete({
          answer: 'done',
          citations: [],
          generatedImage: {
            fileName: 'final.png',
            imagePrompt: 'prompt',
            revisedPrompt: 'revised',
            imageTitle: 'title',
          },
        })
      },
    )

    const promise = runImageGenStream({
      conversationId: 'conv-1',
      question: 'Generate image',
      reactiveMsg,
      timeoutMs: 5000,
    })

    // Two microtask ticks: one for getBrowserFingerprint() resolution,
    // one for the generateImageStream mock to invoke callbacks synchronously.
    await Promise.resolve()
    await Promise.resolve()

    expect(reactiveMsg.imagePartialDataUrl).toBe('https://example.local/final.png')
    expect(reactiveMsg.imagePartialIndex).toBe(0)

    let settled = false
    promise.then(() => {
      settled = true
    })

    vi.advanceTimersByTime(699)
    await Promise.resolve()
    expect(settled).toBe(false)

    vi.advanceTimersByTime(1)
    await expect(promise).resolves.toMatchObject({ answer: 'done' })
  })
})
