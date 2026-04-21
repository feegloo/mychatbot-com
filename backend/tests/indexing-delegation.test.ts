import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock config so we can control indexerUrl/indexerSecret in tests
vi.mock('../src/config.js', () => ({
  config: {
    pythonServerUrl: 'http://localhost:8321',
    indexerUrl: '',
    indexerSecret: '',
  },
}))

// Mock logger to avoid noise
vi.mock('../src/logger.js', () => ({
  default: { info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}))

describe('delegateIndexConversationStream', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('throws when the remote indexer returns a non-OK status', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      text: async () => 'Service Unavailable',
    } as any)

    const { delegateIndexConversationStream } = await import('../src/python/indexing.js')

    const gen = delegateIndexConversationStream({
      conversationId: 'test-conv',
      collectionName: 'col_test',
      files: ['/tmp/test.pdf'],
      indexerUrl: 'http://chatrag-indexer',
      indexerSecret: 'secret',
    })

    await expect(gen.next()).rejects.toThrow('Indexer delegation error (503)')
  })

  it('streams NDJSON events from the remote indexer', async () => {
    const ndjson = [
      JSON.stringify({ event: 'welcome_message', data: { welcome_message: 'Hello' } }),
      JSON.stringify({ event: 'complete', data: { suggested_questions: [] } }),
    ].join('\n') + '\n'

    const encoder = new TextEncoder()
    const encoded = encoder.encode(ndjson)

    // Build a minimal ReadableStream that yields the encoded bytes
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(encoded)
        controller.close()
      },
    })

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body,
    } as any)

    const { delegateIndexConversationStream } = await import('../src/python/indexing.js')

    const gen = delegateIndexConversationStream({
      conversationId: 'test-conv',
      collectionName: 'col_test',
      files: ['/tmp/test.pdf'],
      indexerUrl: 'http://chatrag-indexer',
      indexerSecret: 'secret',
    })

    const events: any[] = []
    for await (const event of gen) {
      events.push(event)
    }

    expect(events).toHaveLength(2)
    expect(events[0].event).toBe('welcome_message')
    expect(events[1].event).toBe('complete')
  })
})
