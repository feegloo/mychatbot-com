import { describe, it, expect } from 'vitest'
import { IMAGE_GEN_REGEX, renderInlineMarkdown, renderMarkdown } from '../../src/utils/markdown'

describe('renderMarkdown table wrapping', () => {
  it('wraps markdown tables in a horizontal scroll container', () => {
    const html = renderMarkdown('| Col A | Col B |\n| --- | --- |\n| A1 | B1 |')

    expect(html).toContain('<div class="markdown-table-scroll"><table>')
    expect(html).toContain('</table></div>')
  })

  it('preserves table attributes when wrapping html tables', () => {
    const html = renderMarkdown('<table class="wide-table"><tr><td>Cell</td></tr></table>')

    expect(html).toContain('<div class="markdown-table-scroll"><table class="wide-table">')
  })

  it('does not add table wrapper when no table exists', () => {
    const html = renderMarkdown('Plain paragraph without table.')

    expect(html).not.toContain('markdown-table-scroll')
  })

  it('wraps markdown images in a horizontal scroll container', () => {
    const html = renderMarkdown('![Generated chart](https://example.com/chart.png)')

    expect(html).toContain('<span class="markdown-image-scroll"><img')
    expect(html).toContain('src="https://example.com/chart.png"')
    expect(html).toContain('alt="Generated chart"')
  })

  it('renders supported color markers', () => {
    const html = renderMarkdown('[c:yellow]warning[/c] [c:gold]highlight[/c] [c:gray]neutral[/c]')

    expect(html).toContain('<span class="text-color-yellow">warning</span>')
    expect(html).toContain('<span class="text-color-gold">highlight</span>')
    expect(html).toContain('<span class="text-color-gray">neutral</span>')
  })

  it('strips unsupported color markers while keeping text', () => {
    const html = renderMarkdown('[c:brown]value[/c]')

    expect(html).toContain('value')
    expect(html).not.toContain('text-color-brown')
  })

  it('renders checklist boxes for shorthand [] syntax', () => {
    const html = renderMarkdown('- [] Feed Aurora\n- [x] Refill water')

    expect(html).toContain('class="checklist-box"')
    expect(html).toContain('class="checklist-box checked"')
  })

  it('does not convert checklist lines to dialogue dashes', () => {
    const html = renderMarkdown('- [ ] First task\n- [ ] Second task')

    expect(html).toContain('class="checklist-box"')
    expect(html).not.toContain('\u2013 [ ]')
  })
})

describe('renderMarkdown measurement unit badges', () => {
  it('badges volume units with munit-vol', () => {
    // Use * bullets so the dialogue-detection heuristic doesn't convert them to prose
    const html = renderMarkdown('* 2 cups flour\n* 1 tbsp olive oil\n* 250 ml water')

    expect(html).toContain('<span class="munit munit-vol">cups</span>')
    expect(html).toContain('<span class="munit munit-vol">tbsp</span>')
    expect(html).toContain('<span class="munit munit-vol">ml</span>')
  })

  it('badges weight units with munit-wt', () => {
    const html = renderMarkdown('* 500 g beef\n* 1.5 kg potatoes\n* 100 mg salt')

    expect(html).toContain('<span class="munit munit-wt">g</span>')
    expect(html).toContain('<span class="munit munit-wt">kg</span>')
    expect(html).toContain('<span class="munit munit-wt">mg</span>')
  })

  it('does not double-badge fl oz as an oz weight unit', () => {
    const html = renderMarkdown('* 4 fl oz cream')

    expect(html).toContain('<span class="munit munit-vol">fl oz</span>')
    // Should NOT also produce a .munit-wt badge for the "oz" inside "fl oz"
    expect(html).not.toContain('munit-wt')
  })

  it('does not add badges to units outside list items', () => {
    const html = renderMarkdown('Add 200 g of sugar to the bowl.')

    expect(html).not.toContain('munit')
  })

  it('does not badge units inside code spans within list items', () => {
    const html = renderMarkdown('* Use `200 g` of butter')

    // The unit is inside a <code> element and must not be badged
    expect(html).not.toContain('munit')
  })

  it('handles nested lists without corrupting outer item badges', () => {
    const md = ['* 1 cup broth', '  * 200 ml water', '  * 50 g noodles'].join('\n')
    const html = renderMarkdown(md)

    // Both levels must be badged and the HTML must remain structurally valid
    expect(html).toContain('<span class="munit munit-vol">cup</span>')
    expect(html).toContain('<span class="munit munit-vol">ml</span>')
    expect(html).toContain('<span class="munit munit-wt">g</span>')
    // Basic structural sanity: opening <li> appears before any closing </li>
    const liOpen = html.indexOf('<li>')
    const liClose = html.indexOf('</li>')
    expect(liOpen).toBeGreaterThanOrEqual(0)
    expect(liOpen).toBeLessThan(liClose)
  })

  it('badges fractional quantities', () => {
    const html = renderMarkdown('* 1/2 cup milk')

    expect(html).toContain('<span class="munit munit-vol">cup</span>')
  })
})

describe('renderInlineMarkdown', () => {
  it('renders italic and bold markdown', () => {
    const html = renderInlineMarkdown('What made _The Alchemist_ **famous**?')

    expect(html).toContain('<em>The Alchemist</em>')
    expect(html).toContain('<strong>famous</strong>')
  })

  it('renders links with safe target attributes', () => {
    const html = renderInlineMarkdown('[Open docs](https://example.com/docs)')

    expect(html).toContain('href="https://example.com/docs"')
    expect(html).toContain('target="_blank"')
    expect(html).toContain('rel="noopener noreferrer"')
  })
})

describe('IMAGE_GEN_REGEX', () => {
  it.each([
    '🎨',
    'generate 🎨',
    'new 🎨',
    'create 🎨 please',
    'Generate image of a cat',
    'create image with sunset',
    'new image',
    'Create an image inspired by Rumi',
    'Make image of a dragon',
    'draw an image',
    'Generate image: dark forest 🎨',
    'generate inspired image: Harry Potter: The Complete Collection - J.K. Rowling',
    'create a new image of a dragon',
    "Make another image about Rumi's desert",
    'wygeneruj obraz inspirowany',
    'wygeneruj obraz zachodu słońca',
    'Wygeneruj obraz inspirowany: mroczny las',
  ])('matches image-generation request %j', (input) => {
    expect(IMAGE_GEN_REGEX.test(input)).toBe(true)
  })

  it.each([
    'Tell me about image processing',
    'What is a new imaginary world?',
    'I imagine a creative scene',
    'Show me the document content',
  ])('does not match non-image request %j', (input) => {
    expect(IMAGE_GEN_REGEX.test(input)).toBe(false)
  })
})
