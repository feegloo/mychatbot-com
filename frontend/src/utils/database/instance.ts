import Dexie from 'dexie'
import { stores } from './tables'

const DATABASE_NAME = 'chatrag'
const DATABASE_VERSION = 1

let database: Dexie | null = null

export function initDatabase(): void {
  if (database) return
  database = new Dexie(DATABASE_NAME)
  database.version(DATABASE_VERSION).stores(stores)
}

export function getDatabase(): Dexie {
  if (!database) {
    throw new Error(`${DATABASE_NAME} database not initialized — call initDatabase() first`)
  }
  return database
}
