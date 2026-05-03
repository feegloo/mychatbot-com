/**
 * Extracts uploadable files (images, PDFs, plain-text files) from a
 * ClipboardEvent.  Plain text strings on the clipboard are intentionally
 * ignored — only actual file items (e.g. screenshots, dragged PDFs) are
 * returned.
 *
 * Returns an empty array when the clipboard carries no supported files so
 * callers can decide whether to call event.preventDefault().
 */

/** Maps base MIME types to canonical file extensions expected by the backend. */
const MIME_TO_EXT: Record<string, string> = {
  'text/plain': 'txt',
}

export function extractPastedFiles(event: ClipboardEvent): File[] {
  const items = event.clipboardData?.items
  if (!items) return []

  const files: File[] = []
  for (const item of Array.from(items)) {
    if (item.kind !== 'file') continue
    const type = item.type
    // Normalise MIME type — strip optional parameters like "; charset=utf-8"
    const baseType = type.split(';')[0].trim()
    if (!baseType.startsWith('image/') && baseType !== 'application/pdf' && baseType !== 'text/plain') continue
    const raw = item.getAsFile()
    if (!raw) continue
    // Screenshots pasted from the OS clipboard have an empty file name.
    // Derive a readable name using the canonical extension for this MIME type.
    if (raw.name) {
      files.push(raw)
    } else {
      const subtype = baseType.split('/')[1] ?? 'bin'
      const ext = MIME_TO_EXT[baseType] ?? subtype
      files.push(new File([raw], `pasted-${Date.now()}.${ext}`, { type: raw.type }))
    }
  }
  return files
}
