import { describe, expect, it } from 'vitest'
import { sanitizeMermaidCode, fixSubgraphNodeConflicts, fixInvalidStadiumCylinderShape, fixInvalidNodeIdChars } from '../../src/utils/mermaidSanitize'

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

describe('fixInvalidStadiumCylinderShape', () => {
  it('converts ((["label"])) to (["label"])', () => {
    const input = `flowchart LR\n  Router((["<b>IE-SR-2GT-LAN</b><br/><small>router Security/NAT/VPN</small>"]))`
    const result = fixInvalidStadiumCylinderShape(input)
    expect(result).toContain('Router(["<b>IE-SR-2GT-LAN</b><br/><small>router Security/NAT/VPN</small>"])')
    expect(result).not.toContain('((["')
  })

  it('converts multiple invalid shapes in one pass', () => {
    const input = [
      'flowchart LR',
      '  A((["Alpha"]))',
      '  B((["Beta"]))',
      '  A --> B',
    ].join('\n')
    const result = fixInvalidStadiumCylinderShape(input)
    expect(result).toContain('A(["Alpha"])')
    expect(result).toContain('B(["Beta"])')
  })

  it('leaves valid stadium shape (["..."]) untouched', () => {
    const input = `flowchart LR\n  A(["valid stadium"])`
    expect(fixInvalidStadiumCylinderShape(input)).toBe(input)
  })

  it('leaves regular quoted rectangle nodes untouched', () => {
    const input = `flowchart LR\n  A["rectangle"]`
    expect(fixInvalidStadiumCylinderShape(input)).toBe(input)
  })
})

describe('sanitizeMermaidCode – stadium/cylinder fix integration', () => {
  it('fixes the IE-SR-2GT-LAN router diagram parse error', () => {
    const input = [
      'flowchart LR',
      '  subgraph Identyfikacja',
      '    Router((["<b>IE-SR-2GT-LAN</b><br/><small>router Security/NAT/VPN</small>"]))',
      '    Order["<b>1345270000</b><br/><small>numer zamówienia</small>"]',
      '  end',
      '  Router ==>|identyfikuje| Order',
    ].join('\n')
    const result = sanitizeMermaidCode(input)
    expect(result).toContain('Router(["<b>IE-SR-2GT-LAN</b><br/><small>router Security/NAT/VPN</small>"])')
    expect(result).not.toContain('(([')
  })
})

describe('sanitizeMermaidCode – mindmap emoji stripping', () => {
  it('strips emoji from mindmap nodes', () => {
    const input = [
      'mindmap',
      '  root((Opieka))',
      '    Karmienie{Posiłki}      🍽️',
      '    Rejestracja{Wniosek}      📝',
    ].join('\n')
    const result = sanitizeMermaidCode(input)
    expect(result).not.toMatch(/🍽/)
    expect(result).not.toMatch(/📝/)
    // Single-brace hexagon nodes are normalised to double-brace by sanitizeMermaidCode
    expect(result).toContain('Karmienie{{Posiłki}}')
    expect(result).toContain('Rejestracja{{Wniosek}}')
  })

  it('strips emoji with variation selector (U+FE0F) from mindmap', () => {
    const input = 'mindmap\n  root((Test))\n    Node\uD83C\uDF7D\uFE0F'
    const result = sanitizeMermaidCode(input)
    expect(result).not.toContain('\uFE0F')
    expect(result).not.toContain('\uD83C\uDF7D')
  })

  it('does not strip emoji from non-mindmap diagrams', () => {
    const input = 'flowchart LR\n  A[test] --> B'
    const result = sanitizeMermaidCode(input)
    expect(result).toBe(input)
  })

  it('preserves newlines when stripping inline emoji (newline-collapse bug)', () => {
    // Emoji stripping must NOT consume the newline after an emoji.
    // If \s* is used instead of [^\S\n]*, the newline + indentation of the
    // next sibling node is swallowed, collapsing two nodes onto one line.
    const input = [
      'mindmap',
      '  root((Post Office))',
      '    novel{{Novel Form}}',
      '      📚 Henry Chinaski',
      '      🏠 Post Office',
    ].join('\n')
    const result = sanitizeMermaidCode(input)
    // Each node must still be on its own line
    const lines = result.split('\n')
    expect(lines.some(l => l.includes('Henry Chinaski'))).toBe(true)
    expect(lines.some(l => l.includes('Post Office') && l.includes('root'))).toBe(true)
    // The two data nodes must NOT be on the same line
    const henryLine = lines.find(l => l.includes('Henry Chinaski'))!
    expect(henryLine).not.toContain('Post Office')
  })

  it('normalises single-brace nodes {Label} to {{Label}} in mindmaps', () => {
    const input = [
      'mindmap',
      '  root((Post Office))',
      '    novel{Novel Form}',
      '    henry((Henry Chinaski))',
    ].join('\n')
    const result = sanitizeMermaidCode(input)
    expect(result).toContain('novel{{Novel Form}}')
    // already-valid double-brace nodes must be left as-is
    expect(result).not.toContain('novel{{{')
  })

  it('leaves double-brace {{Label}} hexagon nodes unchanged', () => {
    const input = [
      'mindmap',
      '  root((Main))',
      '    cat{{Category}}',
    ].join('\n')
    const result = sanitizeMermaidCode(input)
    expect(result).toContain('cat{{Category}}')
    expect(result).not.toContain('cat{{{{')
  })
})

describe('fixInvalidNodeIdChars', () => {
  it('strips ? from a source node ID in an edge line', () => {
    const input = `flowchart LR\n  Chinese? -.->|no link| X`
    const result = fixInvalidNodeIdChars(input)
    expect(result).toContain('Chinese -.->|no link| X')
    expect(result).not.toContain('Chinese?')
  })

  it('strips ? from a target node ID in an edge line', () => {
    const input = `flowchart LR\n  A --> Target?`
    const result = fixInvalidNodeIdChars(input)
    expect(result).toContain('A --> Target')
    expect(result).not.toContain('Target?')
  })

  it('does not affect ? inside an edge label', () => {
    const input = `flowchart LR\n  A -->|is it?| B`
    const result = fixInvalidNodeIdChars(input)
    expect(result).toContain('|is it?|')
  })

  it('does not affect ? inside a quoted node label', () => {
    const input = `flowchart LR\n  A["question?"] --> B`
    const result = fixInvalidNodeIdChars(input)
    expect(result).toContain('"question?"')
  })

  it('handles multiple ? occurrences on one line', () => {
    const input = `flowchart LR\n  A? --> B?`
    const result = fixInvalidNodeIdChars(input)
    expect(result).toContain('A --> B')
    expect(result).not.toContain('?')
  })

  it('is integrated into sanitizeMermaidCode', () => {
    const input = `flowchart LR\n  Chinese? -.->|label| X`
    const result = sanitizeMermaidCode(input)
    expect(result).not.toContain('Chinese?')
    expect(result).toContain('Chinese')
  })
})
