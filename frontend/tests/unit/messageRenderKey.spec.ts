import { describe, expect, it } from 'vitest'
import {
  attachRenderKey,
  buildRenderKeyIndex,
  copyWithStableRenderKeys,
} from '../../src/utils/messageRenderKey'

describe('messageRenderKey', () => {
  it('keeps an optimistic render key after a real message id is assigned', () => {
    const message = attachRenderKey({ role: 'user', content: 'Hello' }, 'local-user:1')

    message.id = 'msg-123'

    const sameMessage = attachRenderKey(message, 'ignored')
    expect(sameMessage.__renderKey).toBe('local-user:1')
  })

  it('reuses existing render keys when rehydrating server messages', () => {
    const existing = buildRenderKeyIndex([
      { id: 'user-1', __renderKey: 'local-user:1' },
      { id: 'assistant-1', __renderKey: 'local-assistant:2' },
    ])

    const hydrated = copyWithStableRenderKeys(
      [
        { id: 'user-1', role: 'user', content: 'Question' },
        { id: 'assistant-1', role: 'assistant', content: 'Answer' },
      ],
      existing,
    )

    expect(hydrated[0].__renderKey).toBe('local-user:1')
    expect(hydrated[1].__renderKey).toBe('local-assistant:2')
  })

  it('falls back to server-derived keys for messages that were not optimistic', () => {
    const hydrated = copyWithStableRenderKeys(
      [{ id: 'server-1', role: 'assistant', content: 'Welcome' }],
      new Map(),
    )

    expect(hydrated[0].__renderKey).toBe('server:server-1')
  })
})