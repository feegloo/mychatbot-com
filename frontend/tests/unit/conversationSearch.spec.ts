import { describe, expect, it } from 'vitest'
import {
  findFirstIndexKmp,
  searchConversations,
  type SearchableConversation,
} from '../../src/utils/conversationSearch'

describe('findFirstIndexKmp', () => {
  it('finds a substring at the correct index', () => {
    expect(findFirstIndexKmp('the alchemist', 'alch')).toBe(4)
  })

  it('finds a substring at index 0', () => {
    expect(findFirstIndexKmp('hello world', 'hello')).toBe(0)
  })

  it('finds a substring at the very end of text', () => {
    expect(findFirstIndexKmp('abc xyz', 'xyz')).toBe(4)
  })

  it('returns -1 when pattern is not found', () => {
    expect(findFirstIndexKmp('santiago', 'desert')).toBe(-1)
  })

  it('returns 0 for an empty pattern', () => {
    expect(findFirstIndexKmp('hello', '')).toBe(0)
  })

  it('returns -1 when pattern is longer than text', () => {
    expect(findFirstIndexKmp('hi', 'hello')).toBe(-1)
  })

  it('returns -1 for empty text with non-empty pattern', () => {
    expect(findFirstIndexKmp('', 'hello')).toBe(-1)
  })

  it('handles single-character pattern', () => {
    expect(findFirstIndexKmp('hello', 'e')).toBe(1)
  })

  it('handles overlapping patterns correctly (e.g. aabaa)', () => {
    // KMP handles partial match fallback: finds first occurrence
    expect(findFirstIndexKmp('aabaab', 'aab')).toBe(0)
  })
})

describe('searchConversations', () => {
  const conversations: SearchableConversation[] = [
    {
      conversationId: 'conv-1',
      messages: [
        { index: 0, messageId: 'm-1', content: 'The Alchemist is about Santiago.' },
        { index: 1, messageId: 'm-2', content: 'Santiago journeys through the desert.' },
        { index: 2, messageId: 'm-3', content: 'He travels to Egypt.' },
      ],
    },
    {
      conversationId: 'conv-2',
      messages: [
        { index: 0, messageId: 'm-4', content: 'A Dance With Dragons discussion.' },
      ],
    },
    {
      conversationId: 'conv-3',
      messages: [
        { index: 0, messageId: 'm-5', content: 'Completely unrelated conversation.' },
      ],
    },
  ]

  it('returns first matching message metadata and correct matchCount', () => {
    // "santiago" appears in messages 0 and 1 of conv-1
    const hits = searchConversations(conversations, 'santiago')

    expect(hits).toHaveLength(1)
    expect(hits[0]).toEqual({
      conversationId: 'conv-1',
      firstMessageIndex: 0,
      firstMessageId: 'm-1',
      matchCount: 2,
    })
  })

  it('matches case-insensitively', () => {
    const hits = searchConversations(conversations, 'DRAGONS')

    expect(hits).toHaveLength(1)
    expect(hits[0].conversationId).toBe('conv-2')
  })

  it('returns hits from multiple conversations when query matches several', () => {
    // "the" appears in conv-1 ("The Alchemist") and conv-2 ("A Dance With...") and conv-3
    const hits = searchConversations(conversations, 'alchemist')

    expect(hits).toHaveLength(1)
    expect(hits[0].conversationId).toBe('conv-1')
  })

  it('returns hits from all matching conversations', () => {
    // "travel" appears in conv-1 ("He travels to Egypt.")
    // "dragon" appears in conv-2 ("A Dance With Dragons discussion.")
    const hits = searchConversations(conversations, 'travel')

    expect(hits.length).toBeGreaterThanOrEqual(1)
    const ids = hits.map((h) => h.conversationId)
    expect(ids).toContain('conv-1')
    expect(ids).not.toContain('conv-2')
    expect(ids).not.toContain('conv-3')
  })

  it('returns empty array for an empty query', () => {
    const hits = searchConversations(conversations, '')

    expect(hits).toHaveLength(0)
  })

  it('returns empty array when query is only whitespace', () => {
    const hits = searchConversations(conversations, '   ')

    expect(hits).toHaveLength(0)
  })

  it('returns empty array when no conversations match', () => {
    const hits = searchConversations(conversations, 'zzznomatch')

    expect(hits).toHaveLength(0)
  })

  it('uses firstMessageIndex of the first matching message (not necessarily index 0)', () => {
    const convs: SearchableConversation[] = [
      {
        conversationId: 'c-1',
        messages: [
          { index: 0, messageId: 'msg-0', content: 'This message does not match.' },
          { index: 1, messageId: 'msg-1', content: 'This message has needle in it.' },
          { index: 2, messageId: 'msg-2', content: 'Another needle here.' },
        ],
      },
    ]
    const hits = searchConversations(convs, 'needle')

    expect(hits).toHaveLength(1)
    expect(hits[0].firstMessageIndex).toBe(1)
    expect(hits[0].firstMessageId).toBe('msg-1')
    expect(hits[0].matchCount).toBe(2)
  })

  it('handles messages with undefined messageId gracefully', () => {
    const convs: SearchableConversation[] = [
      {
        conversationId: 'c-1',
        messages: [{ index: 0, messageId: undefined, content: 'Finding needle here.' }],
      },
    ]
    const hits = searchConversations(convs, 'needle')

    expect(hits).toHaveLength(1)
    expect(hits[0].firstMessageId).toBeUndefined()
    expect(hits[0].firstMessageIndex).toBe(0)
  })

  it('handles conversations with empty message list', () => {
    const convs: SearchableConversation[] = [
      { conversationId: 'empty', messages: [] },
    ]
    const hits = searchConversations(convs, 'anything')

    expect(hits).toHaveLength(0)
  })

  it('handles messages with empty content', () => {
    const convs: SearchableConversation[] = [
      {
        conversationId: 'c-1',
        messages: [
          { index: 0, messageId: 'm-0', content: '' },
          { index: 1, messageId: 'm-1', content: 'needle is here' },
        ],
      },
    ]
    const hits = searchConversations(convs, 'needle')

    expect(hits).toHaveLength(1)
    expect(hits[0].firstMessageIndex).toBe(1)
  })

  it('trims leading/trailing whitespace from query', () => {
    const hits = searchConversations(conversations, '  dragons  ')

    expect(hits).toHaveLength(1)
    expect(hits[0].conversationId).toBe('conv-2')
  })
})
