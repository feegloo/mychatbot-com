import { describe, expect, it } from 'vitest'
import { sanitizeMermaidCode, fixSubgraphNodeConflicts } from '../../src/utils/mermaidSanitize'

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

describe('fixSubgraphNodeConflicts', () => {
  it('returns code unchanged when no conflict exists', () => {
    const input = [
      'flowchart LR',
      '  subgraph RTB',
      '    RTBNode["<b>RTB House</b>"]',
      '    EventSys(["event sourcing"])',
      '  end',
      '  RTBNode ==>|builds| EventSys',
    ].join('\n')
    expect(fixSubgraphNodeConflicts(input)).toBe(input)
  })

  it('renames a node whose ID matches its containing subgraph ID', () => {
    const input = [
      'flowchart LR',
      '  subgraph RTB',
      '    RTB["<b>RTB House</b><br/><small>R&D Architect</small>"]',
      '    EventSys(["event sourcing"])',
      '  end',
      '  RTB ==>|builds| EventSys',
    ].join('\n')
    const result = fixSubgraphNodeConflicts(input)
    // subgraph declaration must remain unchanged
    expect(result).toContain('subgraph RTB')
    // node definition ID is renamed
    expect(result).toContain('RTBNode["<b>RTB House</b><br/><small>R&D Architect</small>"]')
    // edge source is renamed
    expect(result).toContain('RTBNode ==>|builds| EventSys')
    // original bare node ID is gone as a standalone token (edge source line should not start with RTB)
    expect(result).not.toMatch(/^\s*RTB\s*[=\-<]/m)
  })

  it('preserves label text containing the conflicting ID', () => {
    const input = [
      'flowchart LR',
      '  subgraph RTB',
      '    RTB["<b>RTB House</b><br/><small>RTB is the company</small>"]',
      '  end',
    ].join('\n')
    const result = fixSubgraphNodeConflicts(input)
    expect(result).toContain('RTBNode["<b>RTB House</b><br/><small>RTB is the company</small>"]')
  })

  it('renames ID in class statements', () => {
    const input = [
      'flowchart LR',
      '  subgraph RTB',
      '    RTB["<b>RTB House</b>"]',
      '  end',
      '  class RTB entity',
    ].join('\n')
    const result = fixSubgraphNodeConflicts(input)
    expect(result).toContain('class RTBNode entity')
  })

  it('handles multiple conflicting subgraphs independently', () => {
    const input = [
      'flowchart LR',
      '  subgraph Foo',
      '    Foo["<b>Foo Corp</b>"]',
      '  end',
      '  subgraph Bar',
      '    Bar["<b>Bar Inc</b>"]',
      '  end',
      '  Foo --> Bar',
    ].join('\n')
    const result = fixSubgraphNodeConflicts(input)
    expect(result).toContain('subgraph Foo')
    expect(result).toContain('subgraph Bar')
    expect(result).toContain('FooNode["<b>Foo Corp</b>"]')
    expect(result).toContain('BarNode["<b>Bar Inc</b>"]')
    expect(result).toContain('FooNode --> BarNode')
  })
})
