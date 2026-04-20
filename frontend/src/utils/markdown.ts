import { marked } from 'marked'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js'
import 'highlight.js/styles/github-dark-dimmed.min.css'
import katex from 'katex'
import 'katex/dist/katex.min.css'

marked.use({
  breaks: true,
  gfm: true,
  renderer: {
    code({ text, lang }: { text: string; lang?: string }) {
      let highlighted: string
      if (lang && hljs.getLanguage(lang)) {
        highlighted = hljs.highlight(text, { language: lang }).value
      } else {
        highlighted = hljs.highlightAuto(text).value
      }
      const langClass = lang ? ` language-${lang}` : ''
      return `<pre><code class="hljs${langClass}">${highlighted}</code></pre>`
    },
  },
})

/** Strip markdown italic/bold markers from poem lines (poem body is already styled italic) */
function stripPoemInlineMarkers(line: string): string {
  return line
    .replace(/\*\*\*(.+?)\*\*\*/g, '$1')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/__(.+?)__/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/_(.+?)_/g, '$1')
}

function normalizeCitations(text: string): string {
  // Convert bare [N] references to [source:N] format
  // Handles [1][2][3], [1,2,3,4], [1, 2, 3], etc.
  // First: comma-separated like [1,2,3,4] or [1, 2, 3, 4]
  text = text.replace(/\[(\d+(?:\s*,\s*\d+)+)\]/g, (_, nums) =>
    nums
      .split(/\s*,\s*/)
      .map((n: string) => `[source:${n.trim()}]`)
      .join(''),
  )
  // Then: bare single [N] (not already [source:N])
  text = text.replace(/(?<!source:)(?<!\w)\[(\d+)\](?!\()/g, (_, n) => `[source:${n}]`)
  return text
}

export function renderMarkdown(content: string): string {
  let normalized = normalizeCitations(content)

  // Convert dialogue-style "- text" lines to "– text" (en-dash) so they render
  // as plain prose instead of <li> bullets.
  // Heuristic: A block of consecutive "- " lines preceded by a paragraph of
  // narrative text (not another list item) is dialogue, not a real list.
  // Also catch isolated "- text" surrounded by blank lines.
  normalized = normalized.replace(/(?<=^|\n\n)- (.+?)(?=\n\n|$)/g, '– $1')
  // Catch consecutive dialogue lines: a block of "- " lines after a prose paragraph
  normalized = normalized.replace(
    /(?<=^|\n\n)((?:- .+\n?){2,})(?=\n\n|$)/g,
    (_match, block: string) => block.replace(/^- /gm, '– '),
  )

  // Ensure bold-only lines (like filenames) between list items get paragraph separation
  normalized = normalized.replace(
    /^([ \t]*[*\-+] .+)\n(\*\*[^*\n]+\*\*)\n([ \t]*[*\-+] )/gm,
    '$1\n\n$2\n\n$3',
  )
  // Protect LaTeX blocks from marked's processing (underscores, asterisks, etc.)
  const mathPlaceholders: { tex: string; display: boolean }[] = []
  const mathToken = (idx: number) => `\x02MATH${idx}\x02`
  // Display math $$...$$ first (greedy match avoids nesting issues)
  normalized = normalized.replace(/\$\$([^$]+?)\$\$/g, (_, tex) => {
    const i = mathPlaceholders.length
    mathPlaceholders.push({ tex, display: true })
    return mathToken(i)
  })
  // Inline math $...$ (not preceded/followed by word chars, not currency like $10)
  normalized = normalized.replace(/(?<!\w)\$([^\s$][^$\n]*?[^\s$])\$(?!\w)/g, (_, tex) => {
    const i = mathPlaceholders.length
    mathPlaceholders.push({ tex, display: false })
    return mathToken(i)
  })
  // Also catch single-char inline math like $x$
  normalized = normalized.replace(/(?<!\w)\$([^\s$])\$(?!\w)/g, (_, tex) => {
    const i = mathPlaceholders.length
    mathPlaceholders.push({ tex, display: false })
    return mathToken(i)
  })
  // Protect [poem]...[/poem] blocks from marked processing
  const poemPlaceholders: string[] = []
  const poemToken = (idx: number) => `\x03POEM${idx}\x03`
  normalized = normalized.replace(/\[poem\]\s*\n?([\s\S]*?)\[\/poem\]/gi, (_, body) => {
    const i = poemPlaceholders.length
    poemPlaceholders.push(body.trim())
    return poemToken(i)
  })
  // Protect [action:Label] markers from marked (which may interpret
  // square-bracket sequences as reference links and drop or re-encode them,
  // causing the post-DOMPurify regex replacements to miss).
  const actionPlaceholders: string[] = []
  const actionToken = (idx: number) => `\x01ACTION${idx}\x01`
  normalized = normalized.replace(/\[action:\s*([^\]]+)\]/g, (_, label) => {
    const i = actionPlaceholders.length
    actionPlaceholders.push(label.trim())
    return actionToken(i)
  })
  // Protect [upload] markers from marked processing
  const uploadToken = '\x01UPLOAD\x01'
  normalized = normalized.replace(/\[upload\]/gi, uploadToken)

  const rawHtml = marked.parse(normalized, { async: false }) as string
  // Replace disabled checkboxes BEFORE DOMPurify (which may strip <input> tags)
  // Use flexible regex to handle any attribute order from marked
  const withChecklists = rawHtml
    .replace(
      /<input\s+(?=[^>]*type="checkbox")(?=[^>]*disabled="")[^>]*checked=""[^>]*\/?>/gi,
      '<span class="checklist-box checked" role="checkbox" tabindex="0"></span>',
    )
    .replace(
      /<input\s+(?=[^>]*type="checkbox")(?=[^>]*disabled="")[^>]*\/?>/gi,
      '<span class="checklist-box" role="checkbox" tabindex="0"></span>',
    )
  const sanitized = DOMPurify.sanitize(withChecklists)
  // Restore LaTeX blocks and render with KaTeX
  // eslint-disable-next-line no-control-regex
  const withKatex = sanitized.replace(/\x02MATH(\d+)\x02/g, (_, idxStr) => {
    const idx = parseInt(idxStr, 10)
    const { tex, display } = mathPlaceholders[idx]
    try {
      return katex.renderToString(tex, { displayMode: display, throwOnError: false })
    } catch {
      return display ? `$$${tex}$$` : `$${tex}$`
    }
  })
  // Restore [poem] blocks as styled blockquote with decorative quotes
  // eslint-disable-next-line no-control-regex
  const withPoems = withKatex.replace(/\x03POEM(\d+)\x03/g, (_, idxStr) => {
    const idx = parseInt(idxStr, 10)
    const lines = poemPlaceholders[idx]
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean)
      .map((l) => stripPoemInlineMarkers(l))
    const body = lines.join('<br>')
    return `<div class="poem-block"><div class="poem-quote-mark">\u201C</div><div class="poem-body">${body}</div><div class="poem-quote-mark poem-quote-close">\u201D</div></div>`
  })
  // Replace ++underline++ markers with <u> tags
  const withUnderline = withPoems.replace(/\+\+([^+]+)\+\+/g, '<u>$1</u>')
  // Replace [c:color]text[/c] markers with colored spans (whitelist of allowed colors)
  const allowedColors = new Set([
    'green',
    'red',
    'amber',
    'blue',
    'purple',
    'pink',
    'cyan',
    'orange',
    'lime',
    'rose',
  ])
  const withColors = withUnderline.replace(/\[c:(\w+)\](.*?)\[\/c\]/g, (_, color, text) =>
    allowedColors.has(color) ? `<span class="text-color-${color}">${text}</span>` : text,
  )
  // Replace [source:N] or [source:N,N,...] markers with clickable inline source buttons
  const withSources = withColors.replace(/\[source:\s*(\d+(?:,\s*\d+)*)\]/g, (_, nums) =>
    nums
      .split(/,\s*/)
      .map(
        (n: string) =>
          `<button class="inline-source-btn" data-source-idx="${parseInt(n, 10)}">` +
          `<span class="inline-source-icon">↑</span>${n.trim()}</button>`,
      )
      .join(''),
  )
  // Restore [action:Label] placeholders as clickable action buttons
  // eslint-disable-next-line no-control-regex
  const withActions = withSources.replace(/\x01ACTION(\d+)\x01/g, (_, idxStr) => {
    const label = actionPlaceholders[parseInt(idxStr, 10)]
    return `<button class="action-btn" data-action="${label}">${label}</button>`
  })
  // Restore [upload] placeholders as upload action buttons
  // eslint-disable-next-line no-control-regex
  const withUpload = withActions.replace(
    /\x01UPLOAD\x01/g,
    '<button class="action-btn upload-action-btn" data-upload="true">' +
      '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: -2px; margin-right: 4px">' +
      '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>' +
      '<polyline points="17 8 12 3 7 8"/>' +
      '<line x1="12" y1="3" x2="12" y2="15"/>' +
      '</svg>Upload more files</button>',
  )
  // Wrap consecutive action buttons in an inline container (like welcome message pills)
  const withActionsWrapped = withUpload.replace(
    /(<button class="action-btn"[^>]*>.*?<\/button>(?:\s*<button class="action-btn"[^>]*>.*?<\/button>)*)/g,
    '<span class="action-btns-row">$1</span>',
  )
  // Add target="_blank" to all <a> tags that don't already have it
  const withTargetBlank = withActionsWrapped.replace(
    /<a (?![^>]*target=)/gi,
    '<a target="_blank" rel="noopener noreferrer" ',
  )
  // Wrap tables so wide markdown tables can scroll horizontally on narrow screens
  const withScrollableTables = withTargetBlank
    .replace(
      /<table(\s[^>]*)?>/g,
      (_match, attrs: string | undefined) =>
        `<div class="markdown-table-scroll"><table${attrs ?? ''}>`,
    )
    .replace(/<\/table>/g, '</table></div>')
  // Wrap images so wide generated images can scroll horizontally while staying height-limited
  const withScrollableImages = withScrollableTables.replace(
    /<img([^>]*)>/g,
    (_match, attrs: string | undefined) =>
      `<span class="markdown-image-scroll"><img${attrs ?? ''}></span>`,
  )
  // Linkify bare domain URLs in text nodes (not inside existing <a> tags)
  const tlds = 'com|org|net|io|dev|pl|eu|co|info|me|app|xyz|tech|ai'
  const bareDomain = new RegExp(
    `\\b((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\\.)+(?:${tlds}))(\\/[^\\s<"'\u201C\u201D\u2018\u2019\u00AB\u00BB.,;:!?)\\]]*)?`,
    'gi',
  )
  let insideA = 0
  return withScrollableImages.replace(
    /(<a\b[^>]*>)|(<\/a>)|(<[^>]*>)|([^<]+)/gi,
    (m, openA: string, closeA: string, _otherTag: string, text: string) => {
      if (openA) {
        insideA++
        return m
      }
      if (closeA) {
        insideA = Math.max(0, insideA - 1)
        return m
      }
      if (text && insideA === 0) {
        return text.replace(bareDomain, (url: string, domain: string, path: string) => {
          const href = `https://${domain}${path || ''}`
          return `<a href="${href}" target="_blank" rel="noopener noreferrer" style="color: #60a5fa;">${url}</a>`
        })
      }
      return m
    },
  )
}
