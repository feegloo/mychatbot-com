export type MessageWithRenderKey<T extends { id?: string }> = T & {
  __renderKey?: string
}

let renderKeySeed = 0

export function nextMessageRenderKey(prefix = 'local'): string {
  renderKeySeed += 1
  return `${prefix}:${renderKeySeed}`
}

export function buildRenderKeyIndex<T extends { id?: string; __renderKey?: string }>(
  messages: T[],
): Map<string, string> {
  const renderKeysById = new Map<string, string>()
  for (const message of messages) {
    if (message.id && message.__renderKey) {
      renderKeysById.set(message.id, message.__renderKey)
    }
  }
  return renderKeysById
}

export function attachRenderKey<T extends { id?: string; __renderKey?: string }>(
  message: T,
  fallbackKey: string,
): T & { __renderKey: string } {
  if (message.__renderKey) return message as T & { __renderKey: string }
  const renderKey = message.id ? `server:${message.id}` : fallbackKey
  Object.assign(message, { __renderKey: renderKey })
  return message as T & { __renderKey: string }
}

export function copyWithStableRenderKeys<T extends { id?: string }>(
  messages: T[],
  existingRenderKeysById: Map<string, string>,
): Array<T & { __renderKey: string }> {
  return messages.map((message, index) => ({
    ...message,
    __renderKey: message.id
      ? (existingRenderKeysById.get(message.id) ?? `server:${message.id}`)
      : `server-index:${index}`,
  }))
}