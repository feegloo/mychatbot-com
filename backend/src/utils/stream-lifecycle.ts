import type { IncomingMessage, ServerResponse } from 'node:http'

type EventTargetLike = Pick<IncomingMessage, 'once' | 'off'> & Pick<ServerResponse, 'once' | 'off'>

function detachListener(target: EventTargetLike, event: string, listener: () => void) {
  target.off(event as Parameters<EventTargetLike['off']>[0], listener)
}

/**
 * Ensures stream teardown runs once no matter which side of the HTTP
 * connection closes first.
 */
export function bindStreamLifecycle(
  req: IncomingMessage,
  res: ServerResponse,
  teardown: () => void,
): () => void {
  let cleanedUp = false

  const cleanup = () => {
    if (cleanedUp) return
    cleanedUp = true

    detachListener(req, 'aborted', cleanup)
    detachListener(req, 'close', cleanup)
    detachListener(res, 'close', cleanup)
    detachListener(res, 'finish', cleanup)

    teardown()
  }

  req.once('aborted', cleanup)
  req.once('close', cleanup)
  res.once('close', cleanup)
  res.once('finish', cleanup)

  return cleanup
}

export function isStreamClosed(res: ServerResponse): boolean {
  return res.writableEnded || res.destroyed
}