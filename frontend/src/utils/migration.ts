/**
 * One-time migration from localStorage to IndexedDB.
 *
 * Runs on first app load after the IndexedDB upgrade. Reads scattered LS keys,
 * writes them into the appropriate tables, then removes the LS entries.
 *
 * Idempotent: silently skips keys that don't exist in LS.
 */
import {
  ConfigurationsTable,
  TranslationsTable,
  ConversationTokensTable,
  ConversationLanguagesTable,
  ChecklistStatesTable,
} from './database'

const MIGRATION_FLAG_KEY = 'chatrag-idb-migrated'

export async function migrateLocalStorageToIndexedDB(): Promise<void> {
  // Already migrated — skip.
  if (localStorage.getItem(MIGRATION_FLAG_KEY) === '1') return

  try {
    await Promise.all([
      migrateScalarConfigurations(),
      migrateTranslations(),
      migrateConversationTokens(),
      migrateConversationLanguages(),
      migrateChecklistStates(),
    ])

    // Mark migration done. Keep this single flag in LS — it IS a scalar value.
    localStorage.setItem(MIGRATION_FLAG_KEY, '1')
  } catch (err) {
    // Non-fatal: old LS data stays as fallback, migration retries on next load.
    console.warn('[chatrag] LS→IDB migration failed, will retry on next load:', err)
  }
}

// Scalar config keys that map directly to the configurations table.
const SCALAR_CONFIG_KEYS = [
  'homePageLang',
  'sidebarCollapsed',
  'chatrag-fingerprint',
  'chatrag-user-id',
] as const

async function migrateScalarConfigurations(): Promise<void> {
  for (const key of SCALAR_CONFIG_KEYS) {
    const raw = localStorage.getItem(key)
    if (raw !== null) {
      await ConfigurationsTable.set(key, raw)
      localStorage.removeItem(key)
    }
  }
}

async function migrateTranslations(): Promise<void> {
  const prefix = 'translation:'
  const keysToMigrate: string[] = []
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i)
    if (key?.startsWith(prefix)) keysToMigrate.push(key)
  }

  for (const key of keysToMigrate) {
    const value = localStorage.getItem(key)
    if (!value) continue
    // key format: "translation:{lang}:{messageId}"
    const rest = key.slice(prefix.length)
    const sep = rest.indexOf(':')
    if (sep < 0) continue
    const lang = rest.slice(0, sep)
    const messageId = rest.slice(sep + 1)
    await TranslationsTable.set(lang, messageId, value)
    localStorage.removeItem(key)
  }
}

async function migrateConversationTokens(): Promise<void> {
  const raw = localStorage.getItem('conversation-token')
  if (!raw) return
  try {
    const map = JSON.parse(raw) as Record<string, string>
    for (const [conversationId, token] of Object.entries(map)) {
      await ConversationTokensTable.set(conversationId, token)
    }
    localStorage.removeItem('conversation-token')
  } catch {
    // Malformed — skip.
  }
}

async function migrateConversationLanguages(): Promise<void> {
  const raw = localStorage.getItem('conversation-languages')
  if (!raw) return
  try {
    const map = JSON.parse(raw) as Record<string, string>
    for (const [conversationId, language] of Object.entries(map)) {
      await ConversationLanguagesTable.set(conversationId, language)
    }
    localStorage.removeItem('conversation-languages')
  } catch {
    // Malformed — skip.
  }
}

async function migrateChecklistStates(): Promise<void> {
  const raw = localStorage.getItem('data')
  if (!raw) return
  try {
    const bag = JSON.parse(raw) as Record<string, unknown>
    const prefix = 'checklist:'
    const remaining: Record<string, unknown> = {}

    for (const [key, value] of Object.entries(bag)) {
      if (key.startsWith(prefix) && Array.isArray(value)) {
        const messageId = key.slice(prefix.length)
        await ChecklistStatesTable.set(messageId, value as number[])
      } else {
        remaining[key] = value
      }
    }

    if (Object.keys(remaining).length === 0) {
      localStorage.removeItem('data')
    } else {
      localStorage.setItem('data', JSON.stringify(remaining))
    }
  } catch {
    // Malformed — skip.
  }
}
