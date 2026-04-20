import { EventEmitter } from 'node:events'

const emitter = new EventEmitter()
emitter.setMaxListeners(200)

export type ConversationEvent = {
  event: string
  data: Record<string, unknown>
}

export function emitConversationEvent(conversationId: string, event: ConversationEvent) {
  emitter.emit(`conversation:${conversationId}`, event)
}

export function onConversationEvent(
  conversationId: string,
  handler: (evt: ConversationEvent) => void,
): () => void {
  emitter.on(`conversation:${conversationId}`, handler)
  return () => {
    emitter.off(`conversation:${conversationId}`, handler)
  }
}
