import { describe, it, expect } from 'vitest'
import {
  encodeConversationTokens,
  decodeConversationTokens,
  buildConversationsLink,
  CONVERSATIONS_PARAM,
} from '../../src/utils/conversationLink'

const SAMPLE: { conversationId: string; token: string }[] = [
  { conversationId: 'abc123XYZ789', token: 'tok_viewer_abc123' },
  { conversationId: 'def456UVW012', token: 'tok_viewer_def456' },
]

describe('conversationLink', () => {
  describe('encodeConversationTokens', () => {
    it('produces a non-empty URL-safe string', () => {
      const encoded = encodeConversationTokens(SAMPLE)
      expect(typeof encoded).toBe('string')
      expect(encoded.length).toBeGreaterThan(0)
      // base64url characters only — no +, /, or = padding
      expect(encoded).toMatch(/^[A-Za-z0-9_-]+$/)
    })

    it('encodes an empty array without throwing', () => {
      const encoded = encodeConversationTokens([])
      expect(typeof encoded).toBe('string')
    })
  })

  describe('decodeConversationTokens', () => {
    it('round-trips a non-empty array', () => {
      const encoded = encodeConversationTokens(SAMPLE)
      const decoded = decodeConversationTokens(encoded)
      expect(decoded).toEqual(SAMPLE)
    })

    it('round-trips a single entry', () => {
      const single = [{ conversationId: 'x1', token: 'y1' }]
      expect(decodeConversationTokens(encodeConversationTokens(single))).toEqual(single)
    })

    it('returns null for a garbage string', () => {
      expect(decodeConversationTokens('!!!not-valid!!!')).toBeNull()
    })

    it('returns null for a valid base64url that is not the expected shape', () => {
      // Encode plain JSON that is not an array of {conversationId, token}
      const bad = btoa(JSON.stringify({ wrong: true }))
        .replace(/\+/g, '-')
        .replace(/\//g, '_')
        .replace(/=/g, '')
      expect(decodeConversationTokens(bad)).toBeNull()
    })

    it('returns null for an empty string', () => {
      expect(decodeConversationTokens('')).toBeNull()
    })
  })

  describe('buildConversationsLink', () => {
    it('builds a URL with the correct param name and encoded value', () => {
      const link = buildConversationsLink(SAMPLE, 'https://chatrag.app')
      expect(link).toContain(`?${CONVERSATIONS_PARAM}=`)
      // Extracting and decoding the param should give back the original array.
      const paramValue = new URL(link).searchParams.get(CONVERSATIONS_PARAM)!
      expect(decodeConversationTokens(paramValue)).toEqual(SAMPLE)
    })

    it('strips a trailing slash from the base URL', () => {
      const link = buildConversationsLink(SAMPLE, 'https://chatrag.app/')
      expect(link).not.toContain('/?')
      expect(link).toContain('?conversations=')
    })
  })
})
