import { describe, expect, it } from 'vitest'
import { sanitizeMermaidCode } from '../../src/utils/mermaidSanitize'

describe('sanitizeMermaidCode', () => {
  it('quotes a label containing an email address', () => {
    const input = `flowchart LR\n  C3[olek.figiel@gmail.com]`
    const result = sanitizeMermaidCode(input)
    expect(result).toContain('C3["olek.figiel@gmail.com"]')
  })

  it('quotes a label starting with + (phone number)', () => {
    const input = `flowchart LR\n  C2[+48 791 421 067]`
    const result = sanitizeMermaidCode(input)
    expect(result).toContain('C2["+48 791 421 067"]')
  })

  it('leaves already-quoted labels untouched', () => {
    const input = `flowchart LR\n  C3["olek.figiel@gmail.com"]`
    const result = sanitizeMermaidCode(input)
    expect(result).toBe(input)
  })

  it('leaves normal labels without special chars untouched', () => {
    const input = `flowchart LR\n  A1[Aleksander Figiel]`
    const result = sanitizeMermaidCode(input)
    expect(result).toBe(input)
  })

  it('fixes multiple problematic nodes in one pass', () => {
    const input = [
      'flowchart LR',
      '  subgraph Contact',
      '    C1[Warszawa]',
      '    C2[+48 791 421 067]',
      '    C3[olek.figiel@gmail.com]',
      '  end',
    ].join('\n')
    const result = sanitizeMermaidCode(input)
    expect(result).toContain('C1[Warszawa]')
    expect(result).toContain('C2["+48 791 421 067"]')
    expect(result).toContain('C3["olek.figiel@gmail.com"]')
  })
})
