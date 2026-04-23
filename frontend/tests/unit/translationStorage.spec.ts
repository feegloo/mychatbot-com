import { describe, it, expect, beforeEach } from 'vitest'
import {
  getStoredTranslation,
  setStoredTranslation,
} from '../../src/utils/translationStorage'

describe('translationStorage', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('returns null for missing keys', () => {
    expect(getStoredTranslation('pl', 'msg-1')).toBeNull()
  })

  it('round-trips translated content by (lang, messageId)', () => {
    setStoredTranslation('pl', 'msg-1', 'Cześć')
    setStoredTranslation('de', 'msg-1', 'Hallo')
    expect(getStoredTranslation('pl', 'msg-1')).toBe('Cześć')
    expect(getStoredTranslation('de', 'msg-1')).toBe('Hallo')
  })

  it('isolates cache entries per message id', () => {
    setStoredTranslation('pl', 'msg-1', 'A')
    setStoredTranslation('pl', 'msg-2', 'B')
    expect(getStoredTranslation('pl', 'msg-1')).toBe('A')
    expect(getStoredTranslation('pl', 'msg-2')).toBe('B')
  })

  it('no-ops on empty lang or messageId', () => {
    setStoredTranslation('', 'msg-1', 'x')
    setStoredTranslation('pl', '', 'x')
    expect(getStoredTranslation('', 'msg-1')).toBeNull()
    expect(getStoredTranslation('pl', '')).toBeNull()
  })

  it('overwrites existing entries', () => {
    setStoredTranslation('pl', 'msg-1', 'v1')
    setStoredTranslation('pl', 'msg-1', 'v2')
    expect(getStoredTranslation('pl', 'msg-1')).toBe('v2')
  })
})
