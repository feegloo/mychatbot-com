import { getDatabase } from '../instance'
import { Tables } from '../tables'

type TranslationRecord = {
  lang: string
  messageId: string
  translated: string
}

function table() {
  return getDatabase().table<TranslationRecord>(Tables.TRANSLATIONS)
}

export async function get(lang: string, messageId: string): Promise<string | null> {
  const record = await table().get([lang, messageId])
  return record?.translated ?? null
}

export async function set(lang: string, messageId: string, translated: string): Promise<void> {
  await table().put({ lang, messageId, translated })
}

/**
 * Bulk-fetch translations for multiple message IDs in a single transaction.
 * Returns a Map of messageId → translated text for all found entries.
 */
export async function getBulk(
  lang: string,
  messageIds: string[],
): Promise<Map<string, string>> {
  const keys = messageIds.map((id) => [lang, id])
  const records = await table().bulkGet(keys)
  const result = new Map<string, string>()
  records.forEach((record) => {
    if (record) result.set(record.messageId, record.translated)
  })
  return result
}
