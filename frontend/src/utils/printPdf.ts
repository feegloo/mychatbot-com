import type jsPDF from 'jspdf'
import { getConversationToken } from '../api'
import { ensureFontsLoaded, registerFonts, PDF_FONT } from './pdfFonts'

/**
 * Properties we must inline on every SVG element so the serialized SVG is
 * self-contained when rendered via `<img>` for canvas rasterization.
 *
 * When an SVG is loaded via `<img src="data:...">`, external CSS is ignored
 * and `currentColor` / CSS custom property resolution differs from in-document
 * rendering. Mermaid's default styling relies on both, which caused text to
 * disappear in exported PDFs while boxes (with explicit fills) still rendered.
 */
const INLINE_STYLE_PROPS = [
  'fill',
  'stroke',
  'stroke-width',
  'stroke-dasharray',
  'color',
  'font-family',
  'font-size',
  'font-weight',
  'font-style',
  'text-anchor',
  'dominant-baseline',
  'opacity',
  'fill-opacity',
  'stroke-opacity',
] as const

function inlineComputedStyles(root: SVGElement) {
  const all = root.querySelectorAll<SVGElement>('*')
  const apply = (el: SVGElement) => {
    const computed = window.getComputedStyle(el)
    for (const prop of INLINE_STYLE_PROPS) {
      const value = computed.getPropertyValue(prop)
      if (value && value !== 'none' && value !== 'normal') {
        el.style.setProperty(prop, value)
      }
    }
  }
  apply(root)
  all.forEach(apply)
}

/** Render mermaid code to a PNG data URL suitable for embedding in jsPDF. */
async function renderMermaidToPng(
  code: string,
  maxWidth: number,
): Promise<{ dataUrl: string; width: number; height: number } | null> {
  // Off-screen host so the browser lays out the SVG and computes styles.
  // Must be attached to the document with non-zero size for getComputedStyle
  // and text measurement to produce real values.
  const host = document.createElement('div')
  host.style.cssText =
    'position:fixed;left:-10000px;top:0;width:2000px;height:auto;visibility:hidden;pointer-events:none;'
  document.body.appendChild(host)

  try {
    const [{ default: mermaid }] = await Promise.all([import('mermaid')])
    const id = `mermaid-pdf-${Date.now()}-${Math.random().toString(36).slice(2)}`
    mermaid.initialize({
      startOnLoad: false,
      theme: 'default',
      securityLevel: 'strict',
      // Disable HTML labels so SVG uses <text> instead of <foreignObject>.
      // <foreignObject> taints the canvas and prevents PNG export.
      flowchart: { htmlLabels: false, useMaxWidth: false },
      sequence: { useMaxWidth: false },
      themeVariables: {
        nodeBorder: '#666666',
        mainBkg: '#f4f4f4',
        nodeTextColor: '#1a1a1a',
        primaryTextColor: '#1a1a1a',
        secondaryTextColor: '#1a1a1a',
        tertiaryTextColor: '#1a1a1a',
        lineColor: '#666666',
        textColor: '#1a1a1a',
        labelTextColor: '#1a1a1a',
      },
    })
    const { svg } = await mermaid.render(id, code)
    host.innerHTML = svg

    const svgEl = host.querySelector('svg') as SVGSVGElement | null
    if (!svgEl) return null

    // Strip foreignObject (belt-and-suspenders; htmlLabels:false should prevent them)
    svgEl.querySelectorAll('foreignObject').forEach((fo) => fo.remove())

    // Inline every computed style so the serialized SVG does not depend on
    // embedded <style> class resolution or `currentColor` inheritance when
    // rendered inside an <img> element.
    inlineComputedStyles(svgEl)

    // Force readable fill on text nodes as a final guarantee.
    svgEl.querySelectorAll<SVGElement>('text, tspan').forEach((el) => {
      el.setAttribute('fill', '#1a1a1a')
      el.style.setProperty('fill', '#1a1a1a', 'important')
    })

    // Get dimensions from bounding box (reliable after layout), fall back to
    // attributes / viewBox.
    let svgW = 0
    let svgH = 0
    try {
      const bbox = svgEl.getBBox()
      svgW = bbox.width
      svgH = bbox.height
    } catch {
      // noop — fall through to attribute-based sizing below
    }
    if (!svgW || !svgH) {
      svgW = parseFloat(svgEl.getAttribute('width') || '0')
      svgH = parseFloat(svgEl.getAttribute('height') || '0')
    }
    const viewBox = svgEl.getAttribute('viewBox')
    if ((!svgW || !svgH) && viewBox) {
      const parts = viewBox.split(/[\s,]+/).map(Number)
      svgW = parts[2] || 600
      svgH = parts[3] || 400
    }
    if (!svgW) svgW = 600
    if (!svgH) svgH = 400

    // Scale to fit maxWidth (in mm → pixels at 2x for crisp output)
    const pxPerMm = 3.78 // ~96 DPI
    const scale = 2
    const targetWidthPx = maxWidth * pxPerMm * scale
    const ratio = Math.min(targetWidthPx / svgW, 1)
    const canvasW = Math.round(svgW * ratio)
    const canvasH = Math.round(svgH * ratio)

    // Ensure SVG has explicit dimensions for the canvas
    svgEl.setAttribute('width', String(canvasW))
    svgEl.setAttribute('height', String(canvasH))
    if (!viewBox) {
      svgEl.setAttribute('viewBox', `0 0 ${svgW} ${svgH}`)
    }
    // xmlns is required when serializing for <img> consumption.
    if (!svgEl.getAttribute('xmlns')) {
      svgEl.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
    }
    const serialized = new XMLSerializer().serializeToString(svgEl)

    // Use a data URL instead of blob URL for reliable cross-browser SVG→canvas rendering
    const svgDataUrl = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(serialized)}`

    const img = new Image()
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve()
      img.onerror = () => reject(new Error('Failed to load mermaid SVG as image'))
      img.src = svgDataUrl
    })

    const canvas = document.createElement('canvas')
    canvas.width = canvasW
    canvas.height = canvasH
    const ctx = canvas.getContext('2d')!
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, canvasW, canvasH)
    ctx.drawImage(img, 0, 0, canvasW, canvasH)

    const dataUrl = canvas.toDataURL('image/png')
    // Convert canvas pixels back to mm
    const widthMm = canvasW / (pxPerMm * scale)
    const heightMm = canvasH / (pxPerMm * scale)
    return { dataUrl, width: widthMm, height: heightMm }
  } catch (e) {
    console.warn('Failed to render mermaid diagram for PDF:', e)
    return null
  } finally {
    host.remove()
  }
}

type PdfPrintOptions = {
  conversationId?: string
}

type ExportableAssistantMessage = {
  content: string
}

// ── Quiz types (mirror QuizBlock.vue to avoid circular imports) ────────────

type QuizQuestion = {
  q: string
  options: string[]
  correct: number[]
  explanation?: string
}

type QuizData = {
  title: string
  multiple?: boolean
  questions: QuizQuestion[]
}

export type QuizPdfState = {
  selections: Record<number, Set<number>>
  submitted: Record<number, boolean>
  wrongOptions: Record<number, Set<number>>
}

// ── Quiz block extraction (brace-counting, same as splitContent.ts) ────────

function extractQuizBlocks(markdown: string): {
  processed: string
  quizData: (QuizData | null)[]
} {
  const quizData: (QuizData | null)[] = []
  const marker = '[quiz:'
  let result = ''
  let i = 0

  while (i < markdown.length) {
    const start = markdown.indexOf(marker, i)
    if (start === -1) {
      result += markdown.slice(i)
      break
    }
    result += markdown.slice(i, start)
    const jsonStart = start + marker.length
    let depth = 0
    let found = false
    for (let j = jsonStart; j < markdown.length; j++) {
      if (markdown[j] === '{') depth++
      else if (markdown[j] === '}') {
        depth--
        if (depth === 0) {
          let k = j + 1
          while (k < markdown.length && /\s/.test(markdown[k])) k++
          if (k < markdown.length && markdown[k] === ']') {
            const jsonStr = markdown.slice(jsonStart, j + 1).replace(/\[source:\s*\d+\]/g, '')
            try {
              const parsed = JSON.parse(jsonStr) as QuizData
              if (parsed.title && Array.isArray(parsed.questions)) {
                quizData.push(parsed)
              } else {
                quizData.push(null)
              }
            } catch {
              quizData.push(null)
            }
            result += `[QUIZ_BLOCK_${quizData.length - 1}]`
            i = k + 1
            found = true
          }
          break
        }
      }
    }
    if (!found) {
      // Malformed quiz block — keep as-is
      result += markdown.slice(start)
      break
    }
  }

  return { processed: result, quizData }
}

// ── Quiz PDF rendering ─────────────────────────────────────────────────────

function variantLetter(index: number): string {
  return String.fromCharCode(65 + index)
}

function appendQuizToPdf(
  doc: jsPDF,
  quiz: QuizData,
  layout: PdfLayout,
  yRef: YRef,
  state?: QuizPdfState,
) {
  const isMultiple = quiz.multiple === true
  const { marginLeft, contentWidth } = layout

  // Title
  doc.setFont(PDF_FONT, 'bold')
  doc.setFontSize(15)
  doc.setTextColor(0, 0, 0)
  const pdfCleanTitle = quiz.title.replace(/\s*-\s*quiz\s*$/i, '')
  ensureNewPage(doc, yRef, layout, 12)
  doc.text(`${pdfCleanTitle} - Quiz`, marginLeft, yRef.y)
  yRef.y += 7

  // Type subtitle
  doc.setFont(PDF_FONT, 'normal')
  doc.setFontSize(9)
  doc.setTextColor(100, 100, 100)
  const typeLabel = isMultiple
    ? 'Multiple choice \u2014 select all correct answers'
    : 'Single choice \u2014 select one correct answer'
  doc.text(typeLabel, marginLeft, yRef.y)
  yRef.y += 6

  // Name/date line for blank worksheets
  if (!state) {
    doc.setFont(PDF_FONT, 'normal')
    doc.setFontSize(10)
    doc.setTextColor(0, 0, 0)
    doc.text('Name: ___________________________________    Date: _______________', marginLeft, yRef.y)
    yRef.y += 9
  }

  // Questions
  for (let qi = 0; qi < quiz.questions.length; qi++) {
    const q = quiz.questions[qi]
    ensureNewPage(doc, yRef, layout, 30)

    doc.setFont(PDF_FONT, 'bold')
    doc.setFontSize(10)
    doc.setTextColor(0, 0, 0)
    const questionLines = doc.splitTextToSize(`${qi + 1}. ${q.q}`, contentWidth)
    doc.text(questionLines, marginLeft, yRef.y)
    yRef.y += questionLines.length * 4.8 + 2

    doc.setFont(PDF_FONT, 'normal')
    doc.setFontSize(9.5)
    for (let oi = 0; oi < q.options.length; oi++) {
      const optLines = doc.splitTextToSize(`${variantLetter(oi)}. ${q.options[oi]}`, contentWidth - 12)
      ensureNewPage(doc, yRef, layout, optLines.length * 4.5 + 3)

      const boxX = marginLeft + 2
      const boxY = yRef.y - 2.8
      const isChecked = state?.selections[qi]?.has(oi) ?? false
      const isWrong = isChecked && !q.correct.includes(oi)

      doc.setDrawColor(100, 100, 100)
      doc.setLineWidth(0.4)
      if (isMultiple) {
        doc.rect(boxX, boxY, 3, 3)
        if (isChecked) {
          doc.setDrawColor(0, 0, 0)
          doc.setLineWidth(0.6)
          if (isWrong) {
            doc.line(boxX + 0.4, boxY + 0.4, boxX + 2.6, boxY + 2.6)
            doc.line(boxX + 2.6, boxY + 0.4, boxX + 0.4, boxY + 2.6)
          } else {
            doc.line(boxX + 0.5, boxY + 1.5, boxX + 1.2, boxY + 2.4)
            doc.line(boxX + 1.2, boxY + 2.4, boxX + 2.5, boxY + 0.6)
          }
          doc.setLineWidth(0.4)
        }
      } else {
        doc.circle(boxX + 1.5, boxY + 1.5, 1.5)
        if (isChecked) {
          if (isWrong) {
            doc.setDrawColor(0, 0, 0)
            doc.setLineWidth(0.6)
            doc.line(boxX + 0.4, boxY + 0.4, boxX + 2.6, boxY + 2.6)
            doc.line(boxX + 2.6, boxY + 0.4, boxX + 0.4, boxY + 2.6)
            doc.setLineWidth(0.4)
          } else {
            doc.setFillColor(0, 0, 0)
            doc.circle(boxX + 1.5, boxY + 1.5, 0.85, 'F')
          }
        }
      }

      doc.setTextColor(0, 0, 0)
      doc.text(optLines, marginLeft + 9, yRef.y)
      yRef.y += optLines.length * 4.5 + 1.5
    }

    // Explanation (only when state indicates the question was correctly submitted)
    if (state?.submitted[qi] && q.explanation) {
      const allCorrectSelected = q.correct.every((c) => state.selections[qi]?.has(c))
      const noWrong = (state.wrongOptions[qi]?.size ?? 0) === 0
      const showExp = isMultiple ? allCorrectSelected && noWrong : true
      if (showExp) {
        ensureNewPage(doc, yRef, layout, 10)
        doc.setFont(PDF_FONT, 'italic')
        doc.setFontSize(8.5)
        doc.setTextColor(80, 80, 80)
        const expLines = doc.splitTextToSize(q.explanation, contentWidth - 4)
        doc.text(expLines, marginLeft + 2, yRef.y)
        yRef.y += expLines.length * 3.8 + 1.5
        doc.setTextColor(0, 0, 0)
      }
    }

    yRef.y += 3
  }

  // Score summary (only when all submitted via state)
  if (state) {
    const allSubmitted = quiz.questions.every((_, i) => state.submitted[i])
    if (allSubmitted) {
      const correctCount = quiz.questions.filter((q, i) => {
        const sel = state.selections[i] || new Set<number>()
        return q.correct.length === sel.size && q.correct.every((c) => sel.has(c))
      }).length
      ensureNewPage(doc, yRef, layout, 12)
      doc.setFont(PDF_FONT, 'bold')
      doc.setFontSize(11)
      doc.setTextColor(0, 0, 0)
      doc.text(`Score: ${correctCount}/${quiz.questions.length}`, marginLeft, yRef.y)
      yRef.y += 8
    }
  }
}

/**
 * Generates a PDF for a single quiz, optionally with user selection state.
 * Used by QuizBlock.vue's download button.
 */
export async function printQuizAsPdf(
  quiz: QuizData,
  fileName: string,
  state?: QuizPdfState,
) {
  const [{ default: jsPDF }] = await Promise.all([import('jspdf'), ensureFontsLoaded()])
  const doc = new jsPDF({ unit: 'mm', format: 'a4' })
  registerFonts(doc)
  const layout = createLayout(doc)
  const yRef: YRef = { y: 20 }

  appendQuizToPdf(doc, quiz, layout, yRef, state)

  applyWatermark(doc)
  doc.save(fileName)
}

// Color name → RGB tuple matching HTML text-color-* CSS classes in ChatMessage.vue
const COLOR_MAP: Record<string, [number, number, number]> = {
  green:  [134, 239, 172],  // #86efac
  red:    [255, 109, 109],  // #ff6d6d
  yellow: [253, 224,  71],  // #fde047
  blue:   [147, 197, 253],  // #93c5fd
  purple: [196, 181, 253],  // #c4b5fd
  orange: [230, 150,  66],  // #e69642
  gold:   [255, 218, 135],  // #ffda87
  pink:   [249, 168, 212],  // #f9a8d4
  gray:   [148, 163, 184],  // #94a3b8
}

// Matches the most common emoji code-point ranges.
const EMOJI_CHAR_RE = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}]/gu

// Cache emoji PNGs (data URLs) for the lifetime of the browser page.
const emojiPngCache = new Map<string, string>()

async function renderEmojiToPng(emoji: string): Promise<string> {
  if (emojiPngCache.has(emoji)) return emojiPngCache.get(emoji)!
  const size = 64
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')
  let dataUrl = ''
  if (ctx) {
    ctx.font = `${Math.round(size * 0.8)}px serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(emoji, size / 2, size / 2 + 2)
    dataUrl = canvas.toDataURL('image/png')
  }
  emojiPngCache.set(emoji, dataUrl)
  return dataUrl
}

type InlineStyle = 'normal' | 'bold' | 'italic' | 'bolditalic'
type InlineToken = {
  text: string
  style: InlineStyle
  isCode?: boolean
  isStrike?: boolean
  isLink?: boolean
  isEmoji?: boolean
  color?: [number, number, number]
}

type PdfLayout = {
  pageWidth: number
  pageHeight: number
  marginLeft: number
  marginRight: number
  marginBottom: number
  contentWidth: number
}

type YRef = { y: number }

function createLayout(doc: jsPDF): PdfLayout {
  const pageWidth = doc.internal.pageSize.getWidth()
  const pageHeight = doc.internal.pageSize.getHeight()
  const marginLeft = 20
  const marginRight = 20
  const marginBottom = 20
  return {
    pageWidth,
    pageHeight,
    marginLeft,
    marginRight,
    marginBottom,
    contentWidth: pageWidth - marginLeft - marginRight,
  }
}

function ensureNewPage(doc: jsPDF, yRef: YRef, layout: PdfLayout, needed: number) {
  if (yRef.y + needed > layout.pageHeight - layout.marginBottom) {
    doc.addPage()
    yRef.y = 20
  }
}

function combineInlineStyle(base: InlineStyle, token: InlineStyle): InlineStyle {
  if (token === 'normal') return base
  if (token === 'bolditalic') return 'bolditalic'
  if (token === 'bold') {
    return base === 'italic' || base === 'bolditalic' ? 'bolditalic' : 'bold'
  }
  if (token === 'italic') {
    return base === 'bold' || base === 'bolditalic' ? 'bolditalic' : 'italic'
  }
  return base
}

function parseInlineTokensRaw(text: string, color?: [number, number, number]): InlineToken[] {
  const tokens: InlineToken[] = []
  const re =
    /(\[([^\]]+)\]\(([^)]+)\)|\*\*\*([^*]+)\*\*\*|\*\*([^*]+)\*\*|__([^_]+)__|\*([^*]+)\*|_([^_]+)_|~~([^~]+)~~|`([^`]+)`)/g
  let cursor = 0
  let match: RegExpExecArray | null
  while ((match = re.exec(text)) !== null) {
    if (match.index > cursor) {
      tokens.push({ text: text.slice(cursor, match.index), style: 'normal', color })
    }
    if (match[2]) tokens.push({ text: match[2], style: 'normal', isLink: true, color })
    else if (match[4]) tokens.push({ text: match[4], style: 'bolditalic', color })
    else if (match[5] || match[6]) tokens.push({ text: match[5] || match[6], style: 'bold', color })
    else if (match[7] || match[8]) tokens.push({ text: match[7] || match[8], style: 'italic', color })
    else if (match[9]) tokens.push({ text: match[9], style: 'normal', isStrike: true, color })
    else if (match[10]) tokens.push({ text: match[10], style: 'normal', isCode: true, color })
    cursor = re.lastIndex
  }
  if (cursor < text.length) {
    tokens.push({ text: text.slice(cursor), style: 'normal', color })
  }
  // Further split each token at emoji boundaries so emojis become separate pieces.
  return tokens.filter((t) => t.text.length > 0).flatMap(splitAtEmojiChars)
}

function splitAtEmojiChars(token: InlineToken): InlineToken[] {
  // Skip if already an emoji token or contains no emoji.
  if (token.isEmoji) return [token]
  const re = new RegExp(EMOJI_CHAR_RE.source, 'gu')
  const parts: InlineToken[] = []
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(token.text)) !== null) {
    if (m.index > last) parts.push({ ...token, text: token.text.slice(last, m.index) })
    parts.push({ ...token, text: m[0], isEmoji: true })
    last = re.lastIndex
  }
  if (last < token.text.length) parts.push({ ...token, text: token.text.slice(last) })
  return parts.filter((p) => p.text.length > 0)
}

function parseInlineTokens(text: string): InlineToken[] {
  const tokens: InlineToken[] = []
  const colorTagRe = /\[c:(\w+)\]([\s\S]*?)\[\/c(?::\w+)?\]/g
  let cursor = 0
  let match: RegExpExecArray | null
  while ((match = colorTagRe.exec(text)) !== null) {
    if (match.index > cursor) {
      tokens.push(...parseInlineTokensRaw(text.slice(cursor, match.index)))
    }
    const rgb = COLOR_MAP[match[1]]
    tokens.push(...parseInlineTokensRaw(match[2], rgb))
    cursor = colorTagRe.lastIndex
  }
  if (cursor < text.length) {
    tokens.push(...parseInlineTokensRaw(text.slice(cursor)))
  }
  return tokens.filter((t) => t.text.length > 0)
}

type WrappedPiece = InlineToken & { width: number }

function splitTokenPieces(token: InlineToken): InlineToken[] {
  return token.text.split(/(\s+)/).map((part) => ({ ...token, text: part }))
}

function measurePiece(doc: jsPDF, piece: InlineToken, fontSize: number, baseStyle: InlineStyle): number {
  if (piece.isEmoji) {
    // 1pt = 0.353mm; add 20% margin so the emoji doesn't crowd adjacent text.
    return fontSize * 0.353 * 1.2
  }
  doc.setFont(PDF_FONT, combineInlineStyle(baseStyle, piece.style))
  doc.setFontSize(fontSize)
  return doc.getTextWidth(piece.text)
}

function splitLongPiece(
  doc: jsPDF,
  piece: InlineToken,
  fontSize: number,
  baseStyle: InlineStyle,
  maxWidth: number,
): WrappedPiece[] {
  const chars = [...piece.text]
  const out: WrappedPiece[] = []
  let buf = ''
  for (const ch of chars) {
    const candidate = buf + ch
    const candidateWidth = measurePiece(doc, { ...piece, text: candidate }, fontSize, baseStyle)
    if (buf && candidateWidth > maxWidth) {
      out.push({ ...piece, text: buf, width: measurePiece(doc, { ...piece, text: buf }, fontSize, baseStyle) })
      buf = ch
    } else {
      buf = candidate
    }
  }
  if (buf) {
    out.push({ ...piece, text: buf, width: measurePiece(doc, { ...piece, text: buf }, fontSize, baseStyle) })
  }
  return out
}

function wrapInlineTokens(
  doc: jsPDF,
  tokens: InlineToken[],
  maxWidth: number,
  fontSize: number,
  baseStyle: InlineStyle,
): WrappedPiece[][] {
  const lines: WrappedPiece[][] = []
  let current: WrappedPiece[] = []
  let width = 0

  const pushLine = () => {
    if (current.length === 0) return
    lines.push(current)
    current = []
    width = 0
  }

  for (const token of tokens) {
    const pieces = splitTokenPieces(token)
    for (const piece of pieces) {
      if (!piece.text) continue
      let pieceWidth = measurePiece(doc, piece, fontSize, baseStyle)
      if (piece.text.trim().length === 0 && current.length === 0) continue

      if (pieceWidth > maxWidth) {
        const chunks = splitLongPiece(doc, piece, fontSize, baseStyle, maxWidth)
        for (const chunk of chunks) {
          if (width + chunk.width > maxWidth && current.length > 0) pushLine()
          current.push(chunk)
          width += chunk.width
          if (width >= maxWidth - 0.1) pushLine()
        }
        continue
      }

      if (width + pieceWidth > maxWidth && current.length > 0) pushLine()
      if (piece.text.trim().length === 0 && current.length === 0) continue

      current.push({ ...piece, width: pieceWidth })
      width += pieceWidth
    }
  }
  pushLine()
  return lines.length ? lines : [[{ text: '', style: baseStyle, width: 0 }]]
}

async function drawWrappedLine(
  doc: jsPDF,
  line: WrappedPiece[],
  x: number,
  y: number,
  fontSize: number,
  baseStyle: InlineStyle,
) {
  let cx = x
  for (const piece of line) {
    if (piece.isEmoji) {
      const pngData = await renderEmojiToPng(piece.text)
      if (pngData) {
        try {
          doc.addImage(pngData, 'PNG', cx, y - piece.width * 0.9, piece.width, piece.width)
        } catch {
          // Emoji image embedding failed — skip silently rather than breaking the PDF.
        }
      }
      cx += piece.width
      continue
    }

    const style = combineInlineStyle(baseStyle, piece.style)
    doc.setFont(PDF_FONT, style)
    doc.setFontSize(fontSize)

    if (piece.isCode && piece.text.trim()) {
      doc.setFillColor(245, 245, 245)
      doc.setDrawColor(230, 230, 230)
      doc.roundedRect(cx - 0.8, y - fontSize * 0.33, piece.width + 1.6, fontSize * 0.55, 0.6, 0.6, 'FD')
    }

    if (piece.isLink) doc.setTextColor(70, 130, 220)
    else if (piece.color) doc.setTextColor(...piece.color)
    else doc.setTextColor(0, 0, 0)

    doc.text(piece.text, cx, y)

    if (piece.isStrike && piece.text.trim()) {
      doc.setDrawColor(100, 100, 100)
      doc.setLineWidth(0.2)
      doc.line(cx, y - fontSize * 0.2, cx + piece.width, y - fontSize * 0.2)
    }
    if (piece.isLink && piece.text.trim()) {
      doc.setDrawColor(70, 130, 220)
      doc.setLineWidth(0.2)
      doc.line(cx, y + 0.4, cx + piece.width, y + 0.4)
    }

    cx += piece.width
  }
}

async function renderInlineWrappedText(
  doc: jsPDF,
  rawText: string,
  x: number,
  yRef: YRef,
  maxWidth: number,
  layout: PdfLayout,
  opts: { fontSize: number; lineHeight: number; baseStyle: InlineStyle },
) {
  const tokens = parseInlineTokens(rawText)
  const lines = wrapInlineTokens(doc, tokens, maxWidth, opts.fontSize, opts.baseStyle)
  for (const line of lines) {
    ensureNewPage(doc, yRef, layout, opts.lineHeight + 1)
    await drawWrappedLine(doc, line, x, yRef.y, opts.fontSize, opts.baseStyle)
    yRef.y += opts.lineHeight
  }
}

function replaceInlineImagesWithAlt(text: string): string {
  return text.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_, alt: string) => `${alt || 'image'} [image]`)
}

function parseMarkdownImageTarget(rawTarget: string): { alt: string; url: string } | null {
  const match = rawTarget.match(/^\s*!\[([^\]]*)\]\(([^)]+)\)\s*$/)
  if (!match) return null
  const alt = (match[1] || '').trim()
  const target = (match[2] || '').trim()
  if (!target) return null
  const url = target.startsWith('<')
    ? (target.slice(1, target.indexOf('>') > 0 ? target.indexOf('>') : target.length - 1).trim() || target)
    : target.split(/\s+/)[0]
  if (!url) return null
  return { alt, url }
}

function toDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error || new Error('Failed to read image blob'))
    reader.readAsDataURL(blob)
  })
}

function loadImageDimensions(dataUrl: string): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve({ width: img.naturalWidth || img.width, height: img.naturalHeight || img.height })
    img.onerror = () => reject(new Error('Failed to load image dimensions'))
    img.src = dataUrl
  })
}

function normalizeImageUrl(url: string): string {
  if (/^data:/i.test(url)) return url
  if (/^https?:\/\//i.test(url)) return url
  if (/^blob:/i.test(url)) return url
  return new URL(url, window.location.origin).toString()
}

async function loadMarkdownImage(
  imageUrl: string,
  options?: PdfPrintOptions,
): Promise<{ dataUrl: string; format: 'PNG' | 'JPEG' | 'WEBP'; width: number; height: number } | null> {
  try {
    const normalized = normalizeImageUrl(imageUrl)
    if (/^data:/i.test(normalized)) {
      const dims = await loadImageDimensions(normalized)
      const fmt = normalized.includes('image/png')
        ? 'PNG'
        : normalized.includes('image/webp')
          ? 'WEBP'
          : 'JPEG'
      return { dataUrl: normalized, format: fmt, ...dims }
    }

    const headers: Record<string, string> = {}
    if (options?.conversationId) {
      const token = getConversationToken(options.conversationId)
      if (token) headers['x-conversation-token'] = token
    }

    const res = await fetch(normalized, {
      credentials: 'include',
      headers,
    })
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`)
    }
    const blob = await res.blob()
    const dataUrl = await toDataUrl(blob)
    const dims = await loadImageDimensions(dataUrl)
    const mime = (blob.type || '').toLowerCase()
    const format = mime.includes('png') ? 'PNG' : mime.includes('webp') ? 'WEBP' : 'JPEG'
    return { dataUrl, format, ...dims }
  } catch (err) {
    console.warn('Failed to load markdown image for PDF:', err)
    return null
  }
}

async function renderMarkdownBlock(
  doc: jsPDF,
  markdown: string,
  layout: PdfLayout,
  yRef: YRef,
  options?: PdfPrintOptions,
) {
  // Extract and render mermaid blocks.
  const mermaidBlockRe = /```mermaid\s*\n([\s\S]*?)```/g
  const mermaidCodes: string[] = []
  let mermaidMatch: RegExpExecArray | null
  while ((mermaidMatch = mermaidBlockRe.exec(markdown)) !== null) {
    mermaidCodes.push(mermaidMatch[1].trim())
  }
  const mermaidImages = await Promise.all(
    mermaidCodes.map((code) => renderMermaidToPng(code, layout.contentWidth)),
  )

  let mermaidPlaceholderIdx = 0
  const withMermaidPlaceholders = markdown.replace(/```mermaid\s*\n[\s\S]*?```/g, () => {
    return `[MERMAID_DIAGRAM_${mermaidPlaceholderIdx++}]`
  })

  // Extract quiz blocks before line-based processing
  const { processed: withQuizPlaceholders, quizData } = extractQuizBlocks(withMermaidPlaceholders)

  const cleaned = withQuizPlaceholders
    .replace(/\[source:\s*\d+(?:,\s*\d+)*\]/g, '')
    .replace(/\[action:\s*[^\]]+\]/g, '')
    .replace(/<p[^>]*class="image-caption"[^>]*>[\s\S]*?<\/p>/gi, '') // strip HTML image captions

  const poemBlocks: string[][] = []
  let poemIdx = 0
  const withPoemPlaceholders = cleaned.replace(
    /\[poem\]\s*\n?([\s\S]*?)\[\/poem\]/gi,
    (_, body: string) => {
      const pLines = body
        .trim()
        .split('\n')
        .map((line: string) => stripInlineFormatting(line.trim()))
        .filter(Boolean)
      poemBlocks.push(pLines)
      return `[POEM_BLOCK_${poemIdx++}]`
    },
  )

  const lines = withPoemPlaceholders.split('\n')
  let i = 0
  let inCodeBlock = false

  while (i < lines.length) {
    const line = lines[i]

    if (line.trimStart().startsWith('```')) {
      inCodeBlock = !inCodeBlock
      if (!inCodeBlock) yRef.y += 2
      i++
      continue
    }

    if (inCodeBlock) {
      doc.setFont(PDF_FONT, 'normal')
      doc.setFontSize(9)
      const codeLines = doc.splitTextToSize(line || ' ', layout.contentWidth - 8)
      const blockH = codeLines.length * 4 + 2
      ensureNewPage(doc, yRef, layout, blockH)
      doc.setTextColor(60, 60, 60)
      doc.setFillColor(245, 245, 245)
      doc.setDrawColor(220, 220, 220)
      doc.roundedRect(layout.marginLeft, yRef.y - 3, layout.contentWidth, blockH, 1, 1, 'FD')
      doc.text(codeLines, layout.marginLeft + 4, yRef.y)
      yRef.y += blockH + 1
      i++
      continue
    }

    if (line.trim() === '') {
      yRef.y += 3
      i++
      continue
    }

    const mermaidPlaceholder = line.trim().match(/^\[MERMAID_DIAGRAM_(\d+)\]$/)
    if (mermaidPlaceholder) {
      const idx = parseInt(mermaidPlaceholder[1], 10)
      const img = mermaidImages[idx]
      if (img) {
        ensureNewPage(doc, yRef, layout, img.height + 4)
        const imgX = layout.marginLeft + (layout.contentWidth - img.width) / 2
        doc.addImage(img.dataUrl, 'PNG', imgX, yRef.y, img.width, img.height)
        yRef.y += img.height + 4
      } else {
        ensureNewPage(doc, yRef, layout, 6)
        doc.setFont(PDF_FONT, 'italic')
        doc.setFontSize(10)
        doc.setTextColor(120, 120, 120)
        doc.text('[Diagram could not be rendered]', layout.marginLeft, yRef.y)
        yRef.y += 6
      }
      i++
      continue
    }

    const quizPlaceholder = line.trim().match(/^\[QUIZ_BLOCK_(\d+)\]$/)
    if (quizPlaceholder) {
      const idx = parseInt(quizPlaceholder[1], 10)
      const quiz = quizData[idx]
      if (quiz) {
        yRef.y += 4
        appendQuizToPdf(doc, quiz, layout, yRef)
        yRef.y += 4
      }
      i++
      continue
    }

    const poemPlaceholder = line.trim().match(/^\[POEM_BLOCK_(\d+)\]$/)
    if (poemPlaceholder) {
      const idx = parseInt(poemPlaceholder[1], 10)
      const pLines = poemBlocks[idx]
      const lineH = 6
      const quoteMarkH = 8
      const padding = 6
      const blockH = quoteMarkH + pLines.length * lineH + quoteMarkH + padding * 2
      ensureNewPage(doc, yRef, layout, blockH)

      doc.setFillColor(248, 245, 255)
      doc.setDrawColor(210, 195, 250)
      doc.roundedRect(layout.marginLeft, yRef.y - 2, layout.contentWidth, blockH, 3, 3, 'FD')

      yRef.y += padding + 5
      doc.setFont(PDF_FONT, 'normal')
      doc.setFontSize(32)
      doc.setTextColor(167, 139, 250)
      doc.text('\u201C', layout.marginLeft + layout.contentWidth / 2, yRef.y, { align: 'center' })
      yRef.y += quoteMarkH

      doc.setFont(PDF_FONT, 'italic')
      doc.setFontSize(11)
      doc.setTextColor(80, 80, 80)
      for (const pLine of pLines) {
        doc.text(pLine, layout.marginLeft + layout.contentWidth / 2, yRef.y, { align: 'center' })
        yRef.y += lineH
      }

      yRef.y += 2
      doc.setFont(PDF_FONT, 'normal')
      doc.setFontSize(32)
      doc.setTextColor(167, 139, 250)
      doc.text('\u201D', layout.marginLeft + layout.contentWidth / 2, yRef.y, { align: 'center' })
      yRef.y += quoteMarkH + padding
      i++
      continue
    }

    if (/^(\s*[-*_]){3,}\s*$/.test(line)) {
      ensureNewPage(doc, yRef, layout, 6)
      doc.setDrawColor(180, 180, 180)
      doc.setLineWidth(0.3)
      doc.line(layout.marginLeft, yRef.y, layout.pageWidth - layout.marginRight, yRef.y)
      yRef.y += 6
      i++
      continue
    }

    const imageLine = parseMarkdownImageTarget(line)
    if (imageLine) {
      const image = await loadMarkdownImage(imageLine.url, options)
      if (image) {
        const maxImageWidth = layout.contentWidth
        const maxImageHeight = layout.pageHeight - 20 - layout.marginBottom
        const ratio = Math.min(maxImageWidth / image.width, maxImageHeight / image.height, 1)
        const drawW = image.width * ratio
        const drawH = image.height * ratio
        ensureNewPage(doc, yRef, layout, drawH + 4)
        const drawX = layout.marginLeft + (layout.contentWidth - drawW) / 2
        doc.addImage(image.dataUrl, image.format, drawX, yRef.y, drawW, drawH)
        yRef.y += drawH + 3
        if (imageLine.alt) {
          await renderInlineWrappedText(doc, imageLine.alt, layout.marginLeft, yRef, layout.contentWidth, layout, {
            fontSize: 9,
            lineHeight: 4,
            baseStyle: 'italic',
          })
          yRef.y += 2
        }
      } else {
        ensureNewPage(doc, yRef, layout, 6)
        doc.setFont(PDF_FONT, 'italic')
        doc.setFontSize(10)
        doc.setTextColor(120, 120, 120)
        doc.text('[Image could not be rendered]', layout.marginLeft, yRef.y)
        yRef.y += 6
      }
      i++
      continue
    }

    const headingMatch = line.match(/^(#{1,6})\s+(.*)/)
    if (headingMatch) {
      const level = headingMatch[1].length
      const text = replaceInlineImagesWithAlt(headingMatch[2])
      const sizes: Record<number, number> = { 1: 18, 2: 15, 3: 13, 4: 12, 5: 11, 6: 10.5 }
      const fontSize = sizes[level] || 11
      const lineHeight = Math.max(4.5, fontSize * 0.45)
      const spacing = level <= 2 ? 8 : 5

      yRef.y += spacing
      ensureNewPage(doc, yRef, layout, lineHeight + 2)
      await renderInlineWrappedText(doc, text, layout.marginLeft, yRef, layout.contentWidth, layout, {
        fontSize,
        lineHeight,
        baseStyle: 'bold',
      })
      yRef.y += 3
      i++
      continue
    }

    if (line.includes('|') && line.trim().startsWith('|')) {
      const tableLines: string[] = []
      while (i < lines.length && lines[i].includes('|') && lines[i].trim().startsWith('|')) {
        tableLines.push(lines[i])
        i++
      }
      yRef.y = renderTable(doc, tableLines, layout.marginLeft, layout.contentWidth, yRef.y, (needed) =>
        ensureNewPage(doc, yRef, layout, needed),
      )
      yRef.y += 4
      continue
    }

    const checklistMatch = line.match(/^(\s*)[-*+]\s+\[([ xX])\]\s+(.*)/)
    if (checklistMatch) {
      const checked = checklistMatch[2].toLowerCase() === 'x'
      const text = replaceInlineImagesWithAlt(checklistMatch[3])
      ensureNewPage(doc, yRef, layout, 7)
      const boxX = layout.marginLeft + 2
      const boxY = yRef.y - 3
      doc.setLineWidth(0.4)
      if (checked) {
        doc.setDrawColor(34, 197, 94)
        doc.setFillColor(34, 197, 94)
        doc.rect(boxX, boxY, 3.5, 3.5, 'FD')
        doc.setDrawColor(255, 255, 255)
        doc.setLineWidth(0.6)
        doc.line(boxX + 0.6, boxY + 1.75, boxX + 1.4, boxY + 2.8)
        doc.line(boxX + 1.4, boxY + 2.8, boxX + 2.9, boxY + 0.7)
      } else {
        doc.setDrawColor(100, 100, 100)
        doc.rect(boxX, boxY, 3.5, 3.5)
      }
      await renderInlineWrappedText(doc, text, layout.marginLeft + 9, yRef, layout.contentWidth - 12, layout, {
        fontSize: 10.5,
        lineHeight: 4.5,
        baseStyle: 'normal',
      })
      yRef.y += 2
      i++
      continue
    }

    const ulMatch = line.match(/^(\s*)[-*+]\s+(.*)/)
    if (ulMatch) {
      const indent = Math.min(Math.floor(ulMatch[1].length / 2), 3)
      const text = replaceInlineImagesWithAlt(ulMatch[2])
      ensureNewPage(doc, yRef, layout, 7)
      const bulletX = layout.marginLeft + indent * 5
      doc.setFont(PDF_FONT, 'normal')
      doc.setFontSize(10.5)
      doc.setTextColor(0, 0, 0)
      doc.text('•', bulletX, yRef.y)
      await renderInlineWrappedText(doc, text, bulletX + 4, yRef, layout.contentWidth - indent * 5 - 5, layout, {
        fontSize: 10.5,
        lineHeight: 4.5,
        baseStyle: 'normal',
      })
      yRef.y += 2
      i++
      continue
    }

    const olMatch = line.match(/^(\s*)(\d+)[.)]\s+(.*)/)
    if (olMatch) {
      const indent = Math.min(Math.floor(olMatch[1].length / 2), 3)
      const num = olMatch[2]
      const text = replaceInlineImagesWithAlt(olMatch[3])
      ensureNewPage(doc, yRef, layout, 7)
      const numX = layout.marginLeft + indent * 5
      doc.setFont(PDF_FONT, 'normal')
      doc.setFontSize(10.5)
      doc.setTextColor(0, 0, 0)
      doc.text(`${num}.`, numX, yRef.y)
      await renderInlineWrappedText(doc, text, numX + 6, yRef, layout.contentWidth - indent * 5 - 7, layout, {
        fontSize: 10.5,
        lineHeight: 4.5,
        baseStyle: 'normal',
      })
      yRef.y += 2
      i++
      continue
    }

    let paragraph = replaceInlineImagesWithAlt(line)
    while (
      i + 1 < lines.length &&
      lines[i + 1].trim() !== '' &&
      !lines[i + 1].trimStart().startsWith('#') &&
      !lines[i + 1].trimStart().startsWith('```') &&
      !lines[i + 1].trimStart().match(/^[-*+]\s/) &&
      !lines[i + 1].trimStart().match(/^\d+[.)]\s/) &&
      !(lines[i + 1].includes('|') && lines[i + 1].trim().startsWith('|')) &&
      !/^(\s*[-*_]){3,}\s*$/.test(lines[i + 1]) &&
      !parseMarkdownImageTarget(lines[i + 1])
    ) {
      i++
      paragraph += ' ' + replaceInlineImagesWithAlt(lines[i])
    }

    await renderInlineWrappedText(doc, paragraph, layout.marginLeft, yRef, layout.contentWidth, layout, {
      fontSize: 10.5,
      lineHeight: 4.5,
      baseStyle: 'normal',
    })
    yRef.y += 2
    i++
  }
}

function applyWatermark(doc: jsPDF) {
  const totalPages = doc.getNumberOfPages()
  for (let p = 1; p <= totalPages; p++) {
    doc.setPage(p)
    const pw = doc.internal.pageSize.getWidth()
    const ph = doc.internal.pageSize.getHeight()
    doc.setFont(PDF_FONT, 'normal')
    doc.setFontSize(8)
    const prefix = 'created with '
    const link = 'chatrag.app'
    const prefixWidth = doc.getTextWidth(prefix)
    const linkWidth = doc.getTextWidth(link)
    const wmX = pw - 12 - (prefixWidth + linkWidth)
    const wmY = ph - 8
    doc.setTextColor(0, 0, 0)
    const GState = (doc as unknown as { GState: new (opts: { opacity: number }) => unknown }).GState
    doc.setGState(new GState({ opacity: 0.35 }))
    doc.text(prefix, wmX, wmY)
    doc.setTextColor(70, 130, 220)
    doc.textWithLink(link, wmX + prefixWidth, wmY, { url: 'https://chatrag.app' })
    doc.setGState(new GState({ opacity: 1 }))
  }
}

function savePdf(doc: jsPDF, title: string) {
  const safeName = title
    .replace(/[^a-zA-Z0-9\u0080-\uFFFF _-]+/g, '_')
    .replace(/_+/g, '_')
    .slice(0, 100)
  doc.save(`${safeName}.pdf`)
}

/**
 * Generates a PDF for a single markdown message.
 */
export async function printContentAsPdf(markdown: string, title: string, options?: PdfPrintOptions) {
  const [{ default: jsPDF }] = await Promise.all([import('jspdf'), ensureFontsLoaded()])
  const doc = new jsPDF({ unit: 'mm', format: 'a4' })
  registerFonts(doc)

  const layout = createLayout(doc)
  const yRef: YRef = { y: 20 }
  await renderMarkdownBlock(doc, markdown, layout, yRef, options)

  applyWatermark(doc)
  savePdf(doc, title)
}

/**
 * Generates a PDF from assistant messages, starting each message on a new page.
 */
export async function printAssistantMessagesAsPdf(
  messages: ExportableAssistantMessage[],
  title: string,
  options?: PdfPrintOptions,
) {
  const nonEmptyMessages = messages.map((m) => m.content?.trim() || '').filter(Boolean)
  if (!nonEmptyMessages.length) {
    return printContentAsPdf('', title, options)
  }

  const [{ default: jsPDF }] = await Promise.all([import('jspdf'), ensureFontsLoaded()])
  const doc = new jsPDF({ unit: 'mm', format: 'a4' })
  registerFonts(doc)
  const layout = createLayout(doc)

  for (let idx = 0; idx < nonEmptyMessages.length; idx++) {
    if (idx > 0) doc.addPage()
    const yRef: YRef = { y: 20 }
    await renderMarkdownBlock(doc, nonEmptyMessages[idx], layout, yRef, options)
  }

  applyWatermark(doc)
  savePdf(doc, title)
}

/** Strip markdown inline formatting (bold, italic, code, links) to plain text */
function stripInlineFormatting(text: string): string {
  return text
    .replace(/\*\*\*(.+?)\*\*\*/g, '$1') // bold+italic
    .replace(/\*\*(.+?)\*\*/g, '$1') // bold
    .replace(/__(.+?)__/g, '$1') // bold alt
    .replace(/\*(.+?)\*/g, '$1') // italic
    .replace(/_(.+?)_/g, '$1') // italic alt
    .replace(/~~(.+?)~~/g, '$1') // strikethrough
    .replace(/`([^`]+)`/g, '$1') // inline code
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1') // links → text only
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1 [image]') // images
    .replace(/\[c:\w+\]([\s\S]*?)\[\/c(?::\w+)?\]/g, '$1') // color tags → text only
    .trim()
}

/** Render a markdown table using jsPDF drawing primitives.
 *  Cells wrap to multiple lines and row height adapts so text is never clipped.
 *  Returns the Y coordinate after the last row. */
function renderTable(
  doc: jsPDF,
  tableLines: string[],
  marginLeft: number,
  contentWidth: number,
  startY: number,
  checkNewPage: (needed: number) => void,
): number {
  // Parse table rows (skip separator line)
  const rows: string[][] = []
  for (const line of tableLines) {
    const trimmed = line.trim().replace(/^\||\|$/g, '')
    if (/^[\s|:-]+$/.test(trimmed)) continue // separator
    const cells = trimmed.split('|').map((c) => stripInlineFormatting(c.trim()))
    rows.push(cells)
  }
  if (rows.length === 0) return startY

  const colCount = Math.max(...rows.map((r) => r.length))
  // Shrink font for wide (many-column) tables so each cell has room to wrap.
  const fontSize = colCount >= 8 ? 7.5 : colCount >= 6 ? 8.5 : 9.5
  const lineHeight = fontSize * 0.42 // mm per wrapped line
  const cellPaddingX = 1.5
  const cellPaddingY = 2
  const colWidth = contentWidth / colCount
  const textWidth = colWidth - cellPaddingX * 2
  let y = startY

  doc.setFontSize(fontSize)

  for (let ri = 0; ri < rows.length; ri++) {
    const row = rows[ri]
    const isHeaderRow = ri === 0

    doc.setFont(PDF_FONT, isHeaderRow ? 'bold' : 'normal')

    // Pre-wrap every cell and compute this row's height from the tallest cell.
    const wrapped: string[][] = []
    let maxLines = 1
    for (let ci = 0; ci < colCount; ci++) {
      const cellText = row[ci] || ''
      const lines = cellText ? doc.splitTextToSize(cellText, textWidth) : ['']
      wrapped.push(lines)
      if (lines.length > maxLines) maxLines = lines.length
    }
    const rowHeight = maxLines * lineHeight + cellPaddingY * 2

    checkNewPage(rowHeight + 2)

    const rowTop = y - lineHeight

    if (isHeaderRow) {
      doc.setFillColor(240, 240, 240)
      doc.rect(marginLeft, rowTop, contentWidth, rowHeight, 'F')
    }

    doc.setDrawColor(160, 160, 160)
    doc.setLineWidth(0.2)
    doc.rect(marginLeft, rowTop, contentWidth, rowHeight)

    doc.setTextColor(0, 0, 0)

    for (let ci = 0; ci < colCount; ci++) {
      const x = marginLeft + ci * colWidth + cellPaddingX
      if (ci > 0) {
        doc.line(marginLeft + ci * colWidth, rowTop, marginLeft + ci * colWidth, rowTop + rowHeight)
      }
      doc.text(wrapped[ci], x, y)
    }
    y += rowHeight
  }
  return y
}
