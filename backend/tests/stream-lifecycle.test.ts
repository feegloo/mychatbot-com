import { EventEmitter } from 'node:events'
import { describe, expect, it, vi } from 'vitest'
import { bindStreamLifecycle } from '../src/utils/stream-lifecycle.js'

function createStreamSide() {
  return new EventEmitter() as EventEmitter & {
    once: EventEmitter['once']
    off: EventEmitter['off']
  }
}

describe('bindStreamLifecycle', () => {
  it('runs teardown when the response closes', () => {
    const req = createStreamSide()
    const res = createStreamSide()
    const teardown = vi.fn()

    bindStreamLifecycle(req as never, res as never, teardown)
    res.emit('close')

    expect(teardown).toHaveBeenCalledTimes(1)
  })

  it('stays idempotent across multiple shutdown events', () => {
    const req = createStreamSide()
    const res = createStreamSide()
    const teardown = vi.fn()
    const cleanup = bindStreamLifecycle(req as never, res as never, teardown)

    req.emit('aborted')
    req.emit('close')
    res.emit('close')
    res.emit('finish')
    cleanup()

    expect(teardown).toHaveBeenCalledTimes(1)
  })
})