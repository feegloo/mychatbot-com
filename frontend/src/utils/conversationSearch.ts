export type SearchableMessage = {
  messageId: string | undefined
  index: number
  content: string
}

export type SearchableConversation = {
  conversationId: string
  messages: SearchableMessage[]
}

export type ConversationSearchHit = {
  conversationId: string
  firstMessageIndex: number
  firstMessageId?: string
  matchCount: number
}

function normalize(value: string): string {
  return value.toLocaleLowerCase()
}

// Knuth-Morris-Pratt string search. Worst-case O(n + m) for each message.
export function findFirstIndexKmp(text: string, pattern: string): number {
  if (!pattern.length) return 0
  if (!text.length || pattern.length > text.length) return -1

  const lps = new Array(pattern.length).fill(0)
  for (let i = 1, len = 0; i < pattern.length; ) {
    if (pattern[i] === pattern[len]) {
      lps[i++] = ++len
    } else if (len) {
      len = lps[len - 1]
    } else {
      lps[i++] = 0
    }
  }

  for (let i = 0, j = 0; i < text.length; ) {
    if (text[i] === pattern[j]) {
      i++
      j++
      if (j === pattern.length) return i - j
      continue
    }
    if (j) {
      j = lps[j - 1]
    } else {
      i++
    }
  }

  return -1
}

export function searchConversations(
  conversations: SearchableConversation[],
  rawQuery: string,
): ConversationSearchHit[] {
  const query = normalize(rawQuery.trim())
  if (!query) return []

  const hits: ConversationSearchHit[] = []

  for (const conversation of conversations) {
    let firstMatchIndex = -1
    let firstMatchId: string | undefined
    let matchCount = 0

    for (const message of conversation.messages) {
      const messageText = normalize(message.content)
      const matchIndex = findFirstIndexKmp(messageText, query)
      if (matchIndex === -1) continue
      matchCount += 1
      if (firstMatchIndex === -1) {
        firstMatchIndex = message.index
        firstMatchId = message.messageId
      }
    }

    if (firstMatchIndex >= 0) {
      hits.push({
        conversationId: conversation.conversationId,
        firstMessageIndex: firstMatchIndex,
        firstMessageId: firstMatchId,
        matchCount,
      })
    }
  }

  return hits
}
