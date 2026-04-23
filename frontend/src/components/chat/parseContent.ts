/**
 * Pure parser for ChatMessage content. Splits a raw markdown string into
 * an ordered list of tokens that the renderer walks in sequence.
 *
 * Contract:
 *   - `[prompt:Label]` — plain suggested question (rendered as <Action>)
 *   - `[action:Label]` — action prompt (rendered as <MessageContentAction>)
 *   - Everything else is a markdown text chunk (rendered via v-html after
 *     marked + DOMPurify in the consumer).
 *
 * Tokens are returned in document order so the renderer can interleave
 * text between action buttons if the assistant emits them inline.
 */

export type ContentToken =
  | { type: 'text'; value: string }
  | { type: 'prompt'; label: string }
  | { type: 'action'; label: string }

const TOKEN_RE = /\[(prompt|action):([^\]]+)\]/g

export function parseMessageContent(content: string): ContentToken[] {
  if (!content) return []
  const tokens: ContentToken[] = []
  let lastIndex = 0
  for (const match of content.matchAll(TOKEN_RE)) {
    const [full, kind, label] = match
    const start = match.index ?? 0
    if (start > lastIndex) {
      const text = content.slice(lastIndex, start)
      if (text.trim()) tokens.push({ type: 'text', value: text })
    }
    tokens.push({ type: kind as 'prompt' | 'action', label: label.trim() })
    lastIndex = start + full.length
  }
  if (lastIndex < content.length) {
    const text = content.slice(lastIndex)
    if (text.trim()) tokens.push({ type: 'text', value: text })
  }
  return tokens
}

/**
 * Splits parsed tokens into the three buckets the layout needs:
 *   - text blocks (rendered inline)
 *   - visible prompts + visible actions (shown directly)
 *   - overflow actions (grouped under MessageContentActionMore)
 *
 * Visibility rules per user spec:
 *   - welcome message: 3 prompts + 2 actions visible, rest -> overflow
 *   - regular assistant: 2 prompts + 1 action visible, rest -> overflow
 */
export interface SplitTokens {
  text: Array<{ type: 'text'; value: string }>
  visiblePrompts: string[]
  visibleActions: string[]
  overflowActions: string[]
}

export function splitTokens(tokens: ContentToken[], isWelcome: boolean): SplitTokens {
  const promptLimit = isWelcome ? 3 : 2
  const actionLimit = isWelcome ? 2 : 1
  const text: Array<{ type: 'text'; value: string }> = []
  const prompts: string[] = []
  const actions: string[] = []
  for (const t of tokens) {
    if (t.type === 'text') text.push(t)
    else if (t.type === 'prompt') prompts.push(t.label)
    else actions.push(t.label)
  }
  return {
    text,
    visiblePrompts: prompts.slice(0, promptLimit),
    visibleActions: actions.slice(0, actionLimit),
    overflowActions: actions.slice(actionLimit),
  }
}
