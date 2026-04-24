/**
 * Word-reveal "typing" animation for already-rendered text blocks.
 *
 * Unlike a true streaming/typewriter effect we keep the whole response
 * rendered at once (so markdown, code, images and citation buttons are
 * available immediately) and only visually reveal each word left-to-right
 * with a staggered CSS animation. This layers on top of the existing
 * `TextFade` opacity transition without replacing it.
 *
 * Why plain DOM walking instead of a library: every npm candidate either
 * re-types character by character (slow, mangles HTML) or requires us to
 * split text up-front — which conflicts with our `v-html` pipeline through
 * `marked` + DOMPurify. A ~30 line walker is smaller than the footprint
 * of any library we'd pull in.
 */

const WORD_CLASS = 'word-reveal'
const APPLIED_ATTR = 'data-word-reveal'
/** Elements whose text we must NOT split — would break layout or code. */
const SKIP_TAGS = new Set([
  'PRE',
  'CODE',
  'SCRIPT',
  'STYLE',
  'TEXTAREA',
  'SVG',
])

/**
 * Wrap every word inside `root` in a span with a staggered animation delay.
 * Total reveal time is clamped to `maxDurationMs` so huge answers still
 * finish within ~2 seconds.
 *
 * Safe to call multiple times on the same element — we mark the root with
 * `data-word-reveal` and bail out on subsequent calls.
 */
export function applyWordReveal(root: HTMLElement, maxDurationMs = 500): void {
  if (!root || root.getAttribute(APPLIED_ATTR) === '1') return
  root.setAttribute(APPLIED_ATTR, '1')

  // Collect target text nodes via a manual recursion. `createTreeWalker`
  // is underimplemented in happy-dom (used for unit tests), so doing this
  // by hand keeps both environments in sync.
  const textNodes: Text[] = []
  const collect = (parent: Node) => {
    for (const child of Array.from(parent.childNodes)) {
      if (child.nodeType === Node.TEXT_NODE) {
        if (child.nodeValue && child.nodeValue.trim()) textNodes.push(child as Text)
        continue
      }
      if (child.nodeType !== Node.ELEMENT_NODE) continue
      const el = child as Element
      if (SKIP_TAGS.has(el.tagName) || el.classList.contains(WORD_CLASS)) continue
      collect(el)
    }
  }
  collect(root)

  // Pre-split to count words so we can compute eased delays.
  const chunksPerNode: string[][] = textNodes.map((n) =>
    (n.nodeValue ?? '').split(/(\s+)/),
  )
  const wordCount = chunksPerNode.reduce(
    (sum, parts) => sum + parts.filter((p) => p && !/^\s+$/.test(p)).length,
    0,
  )
  if (wordCount === 0) return

  // Ease-in acceleration: delays follow a sqrt curve so the first words
  // appear slowly (large gaps) and later words appear progressively faster
  // (shrinking gaps). Total duration is capped at maxDurationMs.
  // sqrt(i / (n-1)) maps 0→0 and (n-1)→1 with a concave shape.
  const easedDelay = (i: number): number => {
    if (wordCount <= 1) return 0
    return maxDurationMs * Math.sqrt(i / (wordCount - 1))
  }

  let wordIndex = 0
  textNodes.forEach((textNode, i) => {
    const frag = document.createDocumentFragment()
    for (const part of chunksPerNode[i]) {
      if (!part) continue
      if (/^\s+$/.test(part)) {
        frag.appendChild(document.createTextNode(part))
        continue
      }
      const span = document.createElement('span')
      span.className = WORD_CLASS
      span.textContent = part
      span.style.animationDelay = `${easedDelay(wordIndex).toFixed(1)}ms`
      frag.appendChild(span)
      wordIndex++
    }
    textNode.parentNode?.replaceChild(frag, textNode)
  })
}
