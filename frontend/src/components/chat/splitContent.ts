/**
 * Splits raw assistant content into ordered renderable parts:
 *   - text: html string ready for v-html (passed through renderMarkdown)
 *   - quiz: parsed QuizData object
 *   - mermaid: raw mermaid code block
 *
 * Pure function, no Vue dependencies. Quiz blocks use `[quiz:{...json...}]`
 * with brace-counting (the JSON may contain nested braces). Mermaid blocks
 * use the standard ```mermaid``` fenced code block. Both are extracted in
 * document order so the renderer interleaves them correctly between prose.
 */
import { renderMarkdown } from '../../utils/markdown'
import type { QuizData } from '../QuizBlock.vue'

export type ContentPart =
  | { type: 'text'; html: string }
  | { type: 'quiz'; quiz: QuizData; quizIndex: number }
  | { type: 'mermaid'; code: string }

const MERMAID_BLOCK_RE = /```mermaid\s*\n([\s\S]*?)```/g

function splitMermaid(text: string): ContentPart[] {
  const result: ContentPart[] = []
  let lastIdx = 0
  for (const m of text.matchAll(MERMAID_BLOCK_RE)) {
    const before = text.slice(lastIdx, m.index)
    if (before.trim()) result.push({ type: 'text', html: renderMarkdown(before) })
    result.push({ type: 'mermaid', code: m[1].trim() })
    lastIdx = (m.index ?? 0) + m[0].length
  }
  const after = text.slice(lastIdx)
  if (after.trim()) result.push({ type: 'text', html: renderMarkdown(after) })
  return result
}

/**
 * Extract balanced JSON for a `[quiz:{...}]` marker starting at `markerStart`.
 * Returns the index of the closing `]` (so caller can advance past it) and the
 * raw JSON string, or null if the marker is malformed/unterminated.
 */
function extractQuizJson(
  content: string,
  markerStart: number,
  markerLen: number,
): { jsonStr: string; endIndex: number } | null {
  const jsonStart = markerStart + markerLen
  let depth = 0
  for (let i = jsonStart; i < content.length; i++) {
    if (content[i] === '{') depth++
    else if (content[i] === '}') {
      depth--
      if (depth === 0) {
        let j = i + 1
        while (j < content.length && /\s/.test(content[j])) j++
        if (j < content.length && content[j] === ']') {
          return { jsonStr: content.slice(jsonStart, i + 1), endIndex: j }
        }
        return null
      }
    }
  }
  return null
}

function tryParseQuiz(jsonStr: string): QuizData | null {
  // Strip [source:N] citations that would break JSON validity.
  const cleaned = jsonStr.replace(/\[source:\s*\d+\]/g, '')
  try {
    const data = JSON.parse(cleaned) as QuizData
    if (!data.title || !Array.isArray(data.questions)) return null
    for (const q of data.questions) {
      if (!Array.isArray(q.correct)) {
        q.correct = [q.correct as unknown as number]
      }
    }
    if (typeof data.multiple !== 'boolean') {
      data.multiple = data.questions.some((q) => q.correct.length > 1)
    }
    return data
  } catch {
    return null
  }
}

export function splitContent(content: string): ContentPart[] {
  if (!content) return []
  // Defensive normalization: keep parsing stable if the model localized marker keys.
  // Canonical markers are always English and should be emitted as [quiz:...].
  const normalizedContent = content.replace(/\[(?:kwiz|test):/gi, '[quiz:')
  const parts: ContentPart[] = []
  const marker = '[quiz:'
  let lastIndex = 0
  let searchFrom = 0
  let quizCounter = 0

  while (searchFrom < normalizedContent.length) {
    const start = normalizedContent.indexOf(marker, searchFrom)
    if (start === -1) break
    const extracted = extractQuizJson(normalizedContent, start, marker.length)
    if (!extracted) {
      searchFrom = start + marker.length
      continue
    }
    const before = normalizedContent.slice(lastIndex, start)
    if (before.trim()) parts.push(...splitMermaid(before))
    const quiz = tryParseQuiz(extracted.jsonStr)
    if (quiz) {
      parts.push({ type: 'quiz', quiz, quizIndex: quizCounter++ })
    } else {
      // Fallback: render the malformed quiz block as plain text/mermaid.
      parts.push(...splitMermaid(normalizedContent.slice(start, extracted.endIndex + 1)))
    }
    lastIndex = extracted.endIndex + 1
    searchFrom = lastIndex
  }

  const remaining = normalizedContent.slice(lastIndex)
  if (remaining.trim()) parts.push(...splitMermaid(remaining))

  if (!parts.length) {
    parts.push({ type: 'text', html: renderMarkdown(normalizedContent) })
  }
  return parts
}
