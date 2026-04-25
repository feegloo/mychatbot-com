import { describe, expect, it } from 'vitest'

import { buildHelloPayload } from '../../src/hello-response.js'

describe('buildHelloPayload', () => {
  it('returns payload with message from provider', () => {
    const payload = buildHelloPayload(() => 'hello from unit test')

    expect(payload).toEqual({ message: 'hello from unit test' })
  })
})
