import { describe, it, expect } from 'vitest'
import { extractPastedFiles } from '../../src/composables/useFilePaste'

// Helper: build a minimal ClipboardEvent with fake DataTransferItemList
function makeClipboardEvent(items: Array<{ kind: string; type: string; file: File | null }>): ClipboardEvent {
  const dtItems = items.map((item) => ({
    kind: item.kind,
    type: item.type,
    getAsFile: () => item.file,
  })) as unknown as DataTransferItemList

  return {
    clipboardData: { items: dtItems },
    preventDefault: () => {},
  } as unknown as ClipboardEvent
}

function makeFile(name: string, type: string): File {
  return new File(['content'], name, { type })
}

describe('extractPastedFiles', () => {
  it('returns empty array when clipboardData is null', () => {
    const event = { clipboardData: null } as unknown as ClipboardEvent
    expect(extractPastedFiles(event)).toEqual([])
  })

  it('returns empty array when no items match supported types', () => {
    const event = makeClipboardEvent([
      { kind: 'file', type: 'video/mp4', file: makeFile('vid.mp4', 'video/mp4') },
      { kind: 'string', type: 'text/plain', file: null },
    ])
    expect(extractPastedFiles(event)).toEqual([])
  })

  it('accepts image/* files and returns them unchanged', () => {
    const img = makeFile('photo.png', 'image/png')
    const event = makeClipboardEvent([{ kind: 'file', type: 'image/png', file: img }])
    const result = extractPastedFiles(event)
    expect(result).toHaveLength(1)
    expect(result[0]).toBe(img)
  })

  it('accepts application/pdf files and returns them unchanged', () => {
    const pdf = makeFile('doc.pdf', 'application/pdf')
    const event = makeClipboardEvent([{ kind: 'file', type: 'application/pdf', file: pdf }])
    const result = extractPastedFiles(event)
    expect(result).toHaveLength(1)
    expect(result[0]).toBe(pdf)
  })

  it('accepts text/plain files and returns them unchanged when they have a name', () => {
    const txt = makeFile('notes.txt', 'text/plain')
    const event = makeClipboardEvent([{ kind: 'file', type: 'text/plain', file: txt }])
    const result = extractPastedFiles(event)
    expect(result).toHaveLength(1)
    expect(result[0]).toBe(txt)
  })

  it('auto-names unnamed image blobs with .png extension (not "png")', () => {
    const unnamed = new File(['data'], '', { type: 'image/png' })
    const event = makeClipboardEvent([{ kind: 'file', type: 'image/png', file: unnamed }])
    const result = extractPastedFiles(event)
    expect(result).toHaveLength(1)
    expect(result[0].name).toMatch(/^pasted-\d+\.png$/)
  })

  it('auto-names unnamed text/plain blobs with .txt (not .plain)', () => {
    const unnamed = new File(['hello'], '', { type: 'text/plain' })
    const event = makeClipboardEvent([{ kind: 'file', type: 'text/plain', file: unnamed }])
    const result = extractPastedFiles(event)
    expect(result).toHaveLength(1)
    expect(result[0].name).toMatch(/^pasted-\d+\.txt$/)
    expect(result[0].name).not.toContain('.plain')
  })

  it('strips MIME parameters before extension derivation', () => {
    const unnamed = new File(['data'], '', { type: 'image/png' })
    const event = makeClipboardEvent([{ kind: 'file', type: 'image/png; charset=utf-8', file: unnamed }])
    const result = extractPastedFiles(event)
    expect(result).toHaveLength(1)
    expect(result[0].name).toMatch(/^pasted-\d+\.png$/)
  })

  it('skips items where getAsFile() returns null', () => {
    const event = makeClipboardEvent([{ kind: 'file', type: 'image/jpeg', file: null }])
    expect(extractPastedFiles(event)).toEqual([])
  })

  it('handles multiple mixed items, returns only supported file kinds', () => {
    const img = makeFile('shot.jpg', 'image/jpeg')
    const pdf = makeFile('doc.pdf', 'application/pdf')
    const event = makeClipboardEvent([
      { kind: 'string', type: 'text/plain', file: null },
      { kind: 'file', type: 'image/jpeg', file: img },
      { kind: 'file', type: 'video/mp4', file: makeFile('v.mp4', 'video/mp4') },
      { kind: 'file', type: 'application/pdf', file: pdf },
    ])
    const result = extractPastedFiles(event)
    expect(result).toHaveLength(2)
    expect(result[0]).toBe(img)
    expect(result[1]).toBe(pdf)
  })
})
