import { getDatabase } from '../instance'
import { Tables } from '../tables'

type ChecklistStateRecord = {
  messageId: string
  checkedIndices: number[]
}

function table() {
  return getDatabase().table<ChecklistStateRecord>(Tables.CHECKLIST_STATES)
}

export async function get(messageId: string): Promise<number[] | undefined> {
  const record = await table().get(messageId)
  return record?.checkedIndices
}

export async function set(messageId: string, checkedIndices: number[]): Promise<void> {
  await table().put({ messageId, checkedIndices })
}
