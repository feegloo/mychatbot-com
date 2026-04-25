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
  | { type: 'action'; label: string; refFileName?: string }

const TOKEN_RE = /\[(prompt|action):([^\]]+)\]/g

/**
 * Parse a raw action label that may carry an optional `|ref:fileName` suffix.
 * Returns the display label and, if present, the referenced file name.
 * Format: "Visible label|ref:generated-abc123.png"
 */
function parseActionLabel(raw: string): { label: string; refFileName?: string } {
  const refIdx = raw.indexOf('|ref:')
  if (refIdx === -1) return { label: raw }
  return {
    label: raw.slice(0, refIdx).trim(),
    refFileName: raw.slice(refIdx + 5).trim(),
  }
}

export function parseMessageContent(content: string): ContentToken[] {
  if (!content) return []
  const tokens: ContentToken[] = []
  let lastIndex = 0
  for (const match of content.matchAll(TOKEN_RE)) {
    const [full, kind, rawLabel] = match
    const start = match.index ?? 0
    if (start > lastIndex) {
      const text = content.slice(lastIndex, start)
      if (text.trim()) tokens.push({ type: 'text', value: text })
    }
    if (kind === 'action') {
      const { label, refFileName } = parseActionLabel(rawLabel.trim())
      tokens.push({ type: 'action', label, refFileName })
    } else {
      tokens.push({ type: 'prompt', label: rawLabel.trim() })
    }
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
 *   - welcome message: 3 prompts + 5 actions visible, rest -> overflow
 *   - regular assistant: 2 prompts + 3 actions visible, rest -> overflow
 */
export type ActionToken = { label: string; refFileName?: string }

export interface SplitTokens {
  text: Array<{ type: 'text'; value: string }>
  visiblePrompts: string[]
  visibleActions: ActionToken[]
  overflowActions: ActionToken[]
}

export function splitTokens(tokens: ContentToken[], isWelcome: boolean): SplitTokens {
  const promptLimit = isWelcome ? 3 : 2
  const actionLimit = isWelcome ? 5 : 3
  const text: Array<{ type: 'text'; value: string }> = []
  const prompts: string[] = []
  const actions: ActionToken[] = []
  for (const t of tokens) {
    if (t.type === 'text') text.push(t)
    else if (t.type === 'prompt') prompts.push(t.label)
    else actions.push({ label: t.label, refFileName: t.refFileName })
  }
  return {
    text,
    visiblePrompts: prompts.slice(0, promptLimit),
    visibleActions: actions.slice(0, actionLimit),
    overflowActions: actions.slice(actionLimit),
  }
}
