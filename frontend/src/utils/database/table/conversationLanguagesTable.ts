import { getDatabase } from '../instance'
import { Tables } from '../tables'

type ConversationLanguageRecord = {
  conversationId: string
  language: string
}

function table() {
  return getDatabase().table<ConversationLanguageRecord>(Tables.CONVERSATION_LANGUAGES)
}

export async function get(conversationId: string): Promise<string | null> {
  const record = await table().get(conversationId)
  return record?.language ?? null
}

export async function set(conversationId: string, language: string): Promise<void> {
  await table().put({ conversationId, language })
}

export async function remove(conversationId: string): Promise<void> {
  await table().delete(conversationId)
}
