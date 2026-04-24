import { afterEach, describe, expect, it, vi } from 'vitest'
import { generateImageStream } from '../../src/api'

function createStreamResponse(bodyText: string) {
  const encoder = new TextEncoder()
  return {
    ok: true,
    body: new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(bodyText))
        controller.close()
      },
    }),
  }
}

describe('generateImageStream', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('parses partial and complete events separated by CRLF blocks', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      createStreamResponse(
        [
          'event: partial',
          'data: {"b64":"abc123","index":0}',
          '',
          'event: complete',
          'data: {"answer":"done","citations":[]}',
          '',
        ].join('\r\n'),
      ) as unknown as Response,
    )

    const onPartial = vi.fn()
    const onComplete = vi.fn()

    await generateImageStream('conv-1', 'Generate image 🎨', undefined, {
      onPartial,
      onComplete,
    })

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(onPartial).toHaveBeenCalledWith({ b64: 'abc123', index: 0 })
    expect(onComplete).toHaveBeenCalledWith({ answer: 'done', citations: [] })
  })
})