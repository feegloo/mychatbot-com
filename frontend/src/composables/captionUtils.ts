/**
 * Shared utilities for word-level caption animation during TTS playback.
 * Used by both useTextSelectionSpeech (click/select mode) and useAutoRead (auto-play mode).
 */
import type { WordCaption } from '../api'

export type MatchedCaption = {
  caption: WordCaption
  range: Range
  ghostWord: string
}

/**
 * Language → color mapping for the caption glow effect.
 * Returns an RGBA highlight color and a ghost text color.
 */
export function getLanguageColors(lang: string): { highlight: string; ghost: string } {
  const code = lang.split('-')[0].toLowerCase()
  switch (code) {
    case 'pl': // Polish — reddish
      return { highlight: 'rgba(220, 60, 60, 0.22)', ghost: 'rgba(255, 130, 130, 0.85)' }
    case 'fr': // French — blueish
      return { highlight: 'rgba(50, 100, 220, 0.22)', ghost: 'rgba(110, 160, 255, 0.85)' }
    case 'de': // German — dark red
      return { highlight: 'rgba(180, 30, 30, 0.22)', ghost: 'rgba(220, 90, 90, 0.85)' }
    case 'es': // Spanish — orange-yellow
      return { highlight: 'rgba(220, 140, 20, 0.22)', ghost: 'rgba(255, 185, 60, 0.85)' }
    case 'it': // Italian — green
      return { highlight: 'rgba(30, 160, 80, 0.22)', ghost: 'rgba(80, 200, 120, 0.85)' }
    case 'pt': // Portuguese — teal-green
      return { highlight: 'rgba(20, 160, 130, 0.22)', ghost: 'rgba(60, 200, 170, 0.85)' }
    case 'ru': // Russian — deep blue
      return { highlight: 'rgba(30, 60, 200, 0.22)', ghost: 'rgba(90, 130, 255, 0.85)' }
    case 'ja': // Japanese — pink
      return { highlight: 'rgba(210, 60, 140, 0.22)', ghost: 'rgba(255, 120, 180, 0.85)' }
    case 'zh': // Chinese — red
      return { highlight: 'rgba(210, 40, 40, 0.22)', ghost: 'rgba(255, 100, 100, 0.85)' }
    case 'ko': // Korean — sky blue
      return { highlight: 'rgba(30, 150, 210, 0.22)', ghost: 'rgba(80, 190, 255, 0.85)' }
    case 'ar': // Arabic — gold
      return { highlight: 'rgba(200, 160, 10, 0.22)', ghost: 'rgba(255, 200, 50, 0.85)' }
    default: // Default violet (same as existing speech-caption)
      return { highlight: 'rgba(139, 92, 246, 0.18)', ghost: 'rgba(196, 181, 253, 0.75)' }
  }
}

/**
 * Extract individual word Ranges from a DOM Range.
 */
export function extractWordRangesFromRange(parentRange: Range): { word: string; range: Range }[] {
  const results: { word: string; range: Range }[] = []

  if (
    parentRange.startContainer === parentRange.endContainer &&
    parentRange.startContainer.nodeType === Node.TEXT_NODE
  ) {
    const text = parentRange.toString()
    const wordRegex = /[\p{L}\p{N}'\u2019-]+/gu
    let match
    while ((match = wordRegex.exec(text)) !== null) {
      const r = document.createRange()
      r.setStart(parentRange.startContainer, parentRange.startOffset + match.index)
      r.setEnd(parentRange.startContainer, parentRange.startOffset + match.index + match[0].length)
      results.push({ word: match[0], range: r })
    }
    return results
  }

  const ancestor = parentRange.commonAncestorContainer
  const root =
    ancestor.nodeType === Node.TEXT_NODE ? ancestor.parentElement! : (ancestor as HTMLElement)
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)

  let node: Text | null
  while ((node = walker.nextNode() as Text | null)) {
    if (!parentRange.intersectsNode(node)) continue
    const text = node.textContent || ''
    const nodeStart = node === parentRange.startContainer ? parentRange.startOffset : 0
    const nodeEnd = node === parentRange.endContainer ? parentRange.endOffset : text.length

    const wordRegex = /[\p{L}\p{N}'\u2019-]+/gu
    let match
    while ((match = wordRegex.exec(text)) !== null) {
      const ws = match.index
      const we = match.index + match[0].length
      if (ws >= nodeStart && we <= nodeEnd) {
        const r = document.createRange()
        r.setStart(node, ws)
        r.setEnd(node, we)
        results.push({ word: match[0], range: r })
      }
    }
  }

  return results
}

/**
 * Match Whisper word captions to DOM word ranges by fuzzy text comparison.
 */
export function matchCaptionsToWords(
  captions: WordCaption[],
  domWords: { word: string; range: Range }[],
): MatchedCaption[] {
  const result: MatchedCaption[] = []
  let domIdx = 0

  for (const cap of captions) {
    const cleanCap = cap.word.replace(/[^\p{L}\p{N}]/gu, '').toLowerCase()
    if (!cleanCap) continue

    for (let j = domIdx; j < domWords.length; j++) {
      const cleanDom = domWords[j].word.replace(/[^\p{L}\p{N}]/gu, '').toLowerCase()
      if (cleanDom === cleanCap || cleanDom.startsWith(cleanCap) || cleanCap.startsWith(cleanDom)) {
        result.push({ caption: cap, range: domWords[j].range, ghostWord: '' })
        domIdx = j + 1
        break
      }
    }
  }

  return result
}

/**
 * Assign ghost (translated) words proportionally to each matched caption.
 */
export function alignGhosts(matched: MatchedCaption[], translatedText: string): void {
  if (!translatedText || !matched.length) return

  const targetWords = translatedText.split(/\s+/).filter((w) => w.length > 0)
  const n = matched.length
  const m = targetWords.length
  if (!m) return

  for (let i = 0; i < n; i++) {
    const start = Math.round((i * m) / n)
    const end = Math.round(((i + 1) * m) / n)
    matched[i].ghostWord = targetWords.slice(start, Math.max(start + 1, end)).join(' ')
  }
}

/**
 * Create or reuse the caption highlight DOM element.
 */
export function ensureHighlightEl(existing: HTMLElement | null): HTMLElement {
  if (existing) return existing
  const el = document.createElement('div')
  el.className = 'speech-caption-highlight'
  document.body.appendChild(el)
  return el
}

/**
 * Create or reuse the ghost translation DOM element.
 */
export function ensureGhostEl(existing: HTMLElement | null): HTMLElement {
  if (existing) return existing
  const el = document.createElement('div')
  el.className = 'speech-caption-ghost'
  document.body.appendChild(el)
  return el
}

/**
 * Position and show the caption highlight and ghost label for the given matched caption.
 * Colors are driven by the active language.
 */
export function renderCaptionVisuals(
  idx: number,
  matched: MatchedCaption[],
  highlightEl: HTMLElement,
  ghostEl: HTMLElement,
  colors: { highlight: string; ghost: string },
): void {
  if (idx < 0) {
    highlightEl.classList.remove('caption-active')
    ghostEl.classList.remove('caption-active')
    return
  }

  const { range, ghostWord } = matched[idx]
  const rect = range.getBoundingClientRect()
  if (rect.width === 0 && rect.height === 0) return

  const scrollX = window.scrollX
  const scrollY = window.scrollY

  // Apply language-specific colors
  highlightEl.style.background = colors.highlight
  highlightEl.style.setProperty('--caption-glow', colors.highlight.replace(/[\d.]+\)$/, '0.35)'))
  highlightEl.style.left = `${rect.left + scrollX - 2}px`
  highlightEl.style.top = `${rect.top + scrollY - 1}px`
  highlightEl.style.width = `${rect.width + 4}px`
  highlightEl.style.height = `${rect.height + 2}px`
  highlightEl.classList.add('caption-active')

  if (ghostWord) {
    ghostEl.textContent = ghostWord
    ghostEl.style.color = colors.ghost
    ghostEl.classList.add('caption-active')
    void ghostEl.offsetHeight
    const ghostWidth = ghostEl.offsetWidth
    let ghostLeft = rect.left + scrollX + rect.width / 2 - ghostWidth / 2
    if (ghostLeft < scrollX + 4) ghostLeft = scrollX + 4
    if (ghostLeft + ghostWidth > scrollX + window.innerWidth - 4) {
      ghostLeft = scrollX + window.innerWidth - ghostWidth - 4
    }
    let ghostTop = rect.bottom + scrollY + 3
    if (rect.bottom + 20 > window.innerHeight) {
      ghostTop = rect.top + scrollY - 18
    }
    ghostEl.style.left = `${ghostLeft}px`
    ghostEl.style.top = `${ghostTop}px`
  } else {
    ghostEl.classList.remove('caption-active')
  }
}

/**
 * Build a Range spanning all text nodes inside a container element that match the given text.
 * Returns null if no match found.
 */
export function findTextRangeInContainer(
  container: HTMLElement,
  text: string,
): Range | null {
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT)
  const allText: { node: Text; start: number }[] = []
  let fullText = ''

  let node: Text | null
  while ((node = walker.nextNode() as Text | null)) {
    allText.push({ node, start: fullText.length })
    fullText += node.textContent || ''
  }

  // Normalize whitespace for matching
  const normalizedFull = fullText.replace(/\s+/g, ' ')
  const normalizedTarget = text.replace(/\s+/g, ' ').trim()
  const matchIdx = normalizedFull.indexOf(normalizedTarget)
  if (matchIdx < 0) return null

  // Map character positions back to text nodes
  const findNodeAtPos = (pos: number): { node: Text; offset: number } | null => {
    for (let i = allText.length - 1; i >= 0; i--) {
      if (allText[i].start <= pos) {
        return { node: allText[i].node, offset: pos - allText[i].start }
      }
    }
    return null
  }

  const startPos = findNodeAtPos(matchIdx)
  const endPos = findNodeAtPos(matchIdx + normalizedTarget.length)
  if (!startPos || !endPos) return null

  const range = document.createRange()
  range.setStart(startPos.node, startPos.offset)
  range.setEnd(endPos.node, endPos.offset)
  return range
}
