import { describe, it, expect, beforeEach } from 'vitest'
import { applyWordReveal } from '../../src/composables/wordReveal'

describe('applyWordReveal', () => {
  let root: HTMLElement

  beforeEach(() => {
    root = document.createElement('div')
    document.body.appendChild(root)
  })

  it('wraps every word in the text in a .word-reveal span with a staggered delay', () => {
    root.innerHTML = '<p>Hello beautiful world</p>'
    applyWordReveal(root, 300)
    const spans = root.querySelectorAll('.word-reveal')
    expect(spans).toHaveLength(3)
    expect(Array.from(spans).map((s) => s.textContent)).toEqual([
      'Hello',
      'beautiful',
      'world',
    ])
    // First word always starts immediately (delay 0), last word is at maxDuration.
    const d0 = parseFloat((spans[0] as HTMLElement).style.animationDelay)
    const d1 = parseFloat((spans[1] as HTMLElement).style.animationDelay)
    const d2 = parseFloat((spans[2] as HTMLElement).style.animationDelay)
    expect(d0).toBe(0)
    expect(d2).toBeCloseTo(300, 0)
    // Gap between words 0→1 should be larger than gap 1→2 (slow start, fast end).
    expect(d1 - d0).toBeGreaterThan(d2 - d1)
  })

  it('preserves whitespace between words as text nodes', () => {
    root.innerHTML = '<p>one  two</p>'
    applyWordReveal(root)
    const p = root.querySelector('p')!
    // word + ws + word = 3 child nodes
    expect(p.childNodes).toHaveLength(3)
    expect(p.childNodes[1].nodeType).toBe(Node.TEXT_NODE)
    expect(p.childNodes[1].nodeValue).toBe('  ')
  })

  it('skips <pre> and <code> descendants so code blocks stay intact', () => {
    root.innerHTML = '<p>hello <code>const x = 1</code> world</p><pre>raw code</pre>'
    applyWordReveal(root)
    // Only "hello" and "world" should be wrapped.
    const spans = root.querySelectorAll('.word-reveal')
    expect(Array.from(spans).map((s) => s.textContent)).toEqual(['hello', 'world'])
    expect(root.querySelector('code')!.textContent).toBe('const x = 1')
    expect(root.querySelector('pre')!.textContent).toBe('raw code')
  })

  it('is idempotent — a second call on the same root is a no-op', () => {
    root.innerHTML = '<p>alpha beta</p>'
    applyWordReveal(root)
    const firstHtml = root.innerHTML
    applyWordReveal(root)
    expect(root.innerHTML).toBe(firstHtml)
  })

  it('last word delay equals maxDurationMs (sqrt easing spans the full range)', () => {
    root.innerHTML = `<p>${Array.from({ length: 500 }, (_, i) => `w${i}`).join(' ')}</p>`
    applyWordReveal(root, 2000)
    const spans = root.querySelectorAll<HTMLElement>('.word-reveal')
    const lastDelay = parseFloat(spans[spans.length - 1].style.animationDelay)
    expect(lastDelay).toBeCloseTo(2000, 0)
  })
})
