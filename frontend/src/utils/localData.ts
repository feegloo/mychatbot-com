import { ChecklistStatesTable, ConfigurationsTable } from './database'

const CHECKLIST_PREFIX = 'checklist:'

export async function getData<T>(key: string): Promise<T | undefined> {
  if (key.startsWith(CHECKLIST_PREFIX)) {
    const messageId = key.slice(CHECKLIST_PREFIX.length)
    const indices = await ChecklistStatesTable.get(messageId)
    return indices as T | undefined
  }
  return ConfigurationsTable.get<T>(key)
}

export async function setData(key: string, value: unknown): Promise<void> {
  if (key.startsWith(CHECKLIST_PREFIX)) {
    const messageId = key.slice(CHECKLIST_PREFIX.length)
    await ChecklistStatesTable.set(messageId, value as number[])
  } else {
    await ConfigurationsTable.set(key, value)
  }
}
