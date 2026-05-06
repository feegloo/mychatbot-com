/**
 * Mindmap label translation utility.
 *
 * Extracts translatable text labels from Mermaid mindmap code, translates them
 * in a single batch request (preserving emoji and shape markers), then
 * reconstructs the original Mermaid code with translated labels.
 *
 * Results are cached in IndexedDB so subsequent opens of the same mindmap in
 * the same target language skip the API call entirely.
 */
import { translateTexts } from '../api'
import { TranslationsTable } from './database'

/** IndexedDB messageId prefix for mindmap cache entries. */
const MINDMAP_CACHE_PREFIX = 'mindmap:'

/**
 * Parses a mermaid mindmap node content string (everything after leading
 * indentation) into its structural parts so that only the human-readable
 * label is sent for translation while shape markers are preserved verbatim.
 *
 * Handles:
 *   root((label))  root[label]  root{{label}}  root(label)
 *   ((label))      [label]      {{label}}       (label)     >label]
 *   raw text
 */
function parseMindmapNodeContent(content: string): {
  prefix: string
  label: string
  suffix: string
} {
  // root + shape: root((label)), root[label], root{{label}}, root(label)
  const rootMatch = content.match(/^(root\s*)(\({2}|\[|\{{2}|\()(.+?)(\){2}|\]|\}{2}|\))$/)
  if (rootMatch) {
    return {
      prefix: rootMatch[1] + rootMatch[2],
      label: rootMatch[3],
      suffix: rootMatch[4],
    }
  }

  // Shape-only: ((label)), {{label}}, [label], (label), >label]
  const shapeMatch = content.match(/^(\({2}|\[|\{{2}|\(|>)(.+?)(\){2}|\]|\}{2}|\))$/)
  if (shapeMatch) {
    return { prefix: shapeMatch[1], label: shapeMatch[2], suffix: shapeMatch[3] }
  }

  // Raw text — default cloud shape
  return { prefix: '', label: content, suffix: '' }
}

type ParsedLine =
  | { kind: 'skip'; raw: string }
  | { kind: 'node'; indent: string; prefix: string; label: string; suffix: string }

/**
 * Parses all lines of a mermaid mindmap code block.
 * The first `mindmap` keyword line and empty lines are marked as `skip`.
 */
function parseMindmapLines(code: string): ParsedLine[] {
  return code.split('\n').map((raw) => {
    const indentMatch = raw.match(/^([^\S\n]*)/)
    const indent = indentMatch?.[1] ?? ''
    const content = raw.slice(indent.length).trim()

    // Skip: empty, the `mindmap` keyword, or Mermaid comment lines
    if (!content || content === 'mindmap' || content.startsWith('%%')) {
      return { kind: 'skip', raw }
    }

    const { prefix, label, suffix } = parseMindmapNodeContent(content)
    return { kind: 'node', indent, prefix, label, suffix }
  })
}

/**
 * Translates all node labels in a Mermaid mindmap code string to `targetLang`,
 * using IndexedDB to cache the result keyed by `conversationId + targetLang`.
 *
 * - Emoji in labels are preserved (Google Translate ignores them).
 * - Labels are sent in a single positional batch (chunked to ≤ 20 per request).
 * - On any error the original code is returned so the mindmap still renders.
 */
export async function translateMindmapCode(
  mermaidCode: string,
  targetLang: string,
  conversationId: string,
  sourceLang?: string,
): Promise<string> {
  const cacheMessageId = MINDMAP_CACHE_PREFIX + conversationId

  // Check IndexedDB cache first
  try {
    const cached = await TranslationsTable.get(targetLang, cacheMessageId)
    if (cached) return cached
  } catch {
    // Cache miss or unavailable — proceed with translation
  }

  const parsedLines = parseMindmapLines(mermaidCode)
  const nodeIndices: number[] = []
  const labels: string[] = []

  parsedLines.forEach((line, i) => {
    if (line.kind === 'node' && line.label) {
      nodeIndices.push(i)
      labels.push(line.label)
    }
  })

  if (!labels.length) return mermaidCode

  try {
    // Batch translate in chunks of 20 (API limit)
    const translated: string[] = []
    for (let start = 0; start < labels.length; start += 20) {
      const chunk = labels.slice(start, start + 20)
      const { translations } = await translateTexts(chunk, targetLang, sourceLang)
      translated.push(...translations)
    }

    const resultLines = parsedLines.map((line, i) => {
      if (line.kind === 'skip') return line.raw
      const j = nodeIndices.indexOf(i)
      const translatedLabel = j >= 0 ? (translated[j] ?? line.label) : line.label
      return line.indent + line.prefix + translatedLabel + line.suffix
    })

    const translatedCode = resultLines.join('\n')

    // Persist to IndexedDB
    try {
      await TranslationsTable.set(targetLang, cacheMessageId, translatedCode)
    } catch {
      // Quota exceeded or storage error — non-fatal
    }

    return translatedCode
  } catch {
    // Translation request failed — return original so mindmap still renders
    return mermaidCode
  }
}
