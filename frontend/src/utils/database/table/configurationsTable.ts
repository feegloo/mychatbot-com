import { getDatabase } from '../instance'
import { Tables } from '../tables'

type ConfigurationRecord = {
  key: string
  value: unknown
}

function table() {
  return getDatabase().table<ConfigurationRecord>(Tables.CONFIGURATIONS)
}

export async function get<T>(key: string): Promise<T | undefined> {
  const record = await table().get(key)
  return record?.value as T | undefined
}

export async function set(key: string, value: unknown): Promise<void> {
  await table().put({ key, value })
}

export async function remove(key: string): Promise<void> {
  await table().delete(key)
}
