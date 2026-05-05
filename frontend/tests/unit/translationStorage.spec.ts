import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  getStoredTranslation,
  setStoredTranslation,
} from '../../src/utils/translationStorage'

// In-memory store backing the mocked TranslationsTable in tests.
const translationStore = new Map<string, string>()

vi.mock('../../src/utils/database', () => ({
  TranslationsTable: {
    get: vi.fn(async (lang: string, messageId: string) =>
      translationStore.get(`${lang}:${messageId}`) ?? null,
    ),
    set: vi.fn(async (lang: string, messageId: string, text: string) => {
      translationStore.set(`${lang}:${messageId}`, text)
    }),
    getBulk: vi.fn(async (lang: string, messageIds: string[]) => {
      const result = new Map<string, string>()
      for (const id of messageIds) {
        const val = translationStore.get(`${lang}:${id}`)
        if (val !== undefined) result.set(id, val)
      }
      return result
    }),
  },
}))

describe('translationStorage', () => {
  beforeEach(() => {
    translationStore.clear()
  })

  it('returns null for missing keys', async () => {
    expect(await getStoredTranslation('pl', 'msg-1')).toBeNull()
  })

  it('round-trips translated content by (lang, messageId)', async () => {
    await setStoredTranslation('pl', 'msg-1', 'Cześć')
    await setStoredTranslation('de', 'msg-1', 'Hallo')
    expect(await getStoredTranslation('pl', 'msg-1')).toBe('Cześć')
    expect(await getStoredTranslation('de', 'msg-1')).toBe('Hallo')
  })

  it('isolates cache entries per message id', async () => {
    await setStoredTranslation('pl', 'msg-1', 'A')
    await setStoredTranslation('pl', 'msg-2', 'B')
    expect(await getStoredTranslation('pl', 'msg-1')).toBe('A')
    expect(await getStoredTranslation('pl', 'msg-2')).toBe('B')
  })

  it('no-ops on empty lang or messageId', async () => {
    await setStoredTranslation('', 'msg-1', 'x')
    await setStoredTranslation('pl', '', 'x')
    expect(await getStoredTranslation('', 'msg-1')).toBeNull()
    expect(await getStoredTranslation('pl', '')).toBeNull()
  })

  it('overwrites existing entries', async () => {
    await setStoredTranslation('pl', 'msg-1', 'v1')
    await setStoredTranslation('pl', 'msg-1', 'v2')
    expect(await getStoredTranslation('pl', 'msg-1')).toBe('v2')
  })
})
