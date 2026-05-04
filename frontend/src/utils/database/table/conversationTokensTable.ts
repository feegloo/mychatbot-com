import { getDatabase } from '../instance'
import { Tables } from '../tables'

type ConversationTokenRecord = {
  conversationId: string
  token: string
}

function table() {
  return getDatabase().table<ConversationTokenRecord>(Tables.CONVERSATION_TOKENS)
}

export async function get(conversationId: string): Promise<string | null> {
  const record = await table().get(conversationId)
  return record?.token ?? null
}

export async function set(conversationId: string, token: string): Promise<void> {
  await table().put({ conversationId, token })
}

export async function getAllIds(): Promise<string[]> {
  const records = await table().toArray()
  return records.map((r) => r.conversationId)
}

export async function remove(conversationId: string): Promise<void> {
  await table().delete(conversationId)
}
