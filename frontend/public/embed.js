/**
 * ChatRAG Embed Widget
 *
 * One-line embed for any website. Shows a chat circle button (bottom-right)
 * that opens an iframe conversation when clicked.
 *
 * Usage:
 *   <script src="https://chatrag.app/embed.js"
 *           data-conversation="https://chatrag.app/c/YOUR_ID"></script>
 */
;(function () {
  'use strict'

  const VALID_CONVERSATION_RE = /^https:\/\/chatrag\.app\/c\/([A-Za-z0-9_-]+)$/
  const ROOT_ID = '__chatrag_embed__'

  // ── Resolve the script tag that loaded us ───────────────────────────────────

  const scriptEl =
    document.currentScript ||
    document.querySelector('script[data-conversation][src*="chatrag.app/embed.js"]')

  const rawUrl = scriptEl && scriptEl.getAttribute('data-conversation')

  if (!rawUrl) {
    console.error(
      '[ChatRAG] Missing data-conversation attribute.\n' +
        'Usage: <script src="https://chatrag.app/embed.js" data-conversation="https://chatrag.app/c/YOUR_ID"></script>',
    )
    return
  }

  const match = rawUrl.trim().match(VALID_CONVERSATION_RE)
  if (!match) {
    console.error(
      '[ChatRAG] Invalid conversation URL: "' +
        rawUrl +
        '".\n' +
        'Must be: https://chatrag.app/c/{conversationId}\n' +
        'Invalid examples: https://chatrag.app, https://chatrag.app/m/..., etc.',
    )
    return
  }

  const conversationId = match[1]
  const embedUrl = 'https://chatrag.app/c/' + conversationId + '?embed=1'

  // ── Validate conversation exists before mounting the widget ─────────────────

  fetch('https://chatrag.app/api/conversations/' + conversationId, { method: 'GET' })
    .then(function (res) {
      if (res.status === 404) {
        console.error(
          '[ChatRAG] Conversation not found (404): ' + rawUrl + '\n' +
            'Check the URL is correct and the conversation is accessible.',
        )
        return
      }
      // Any non-404 response (200, 401, etc.) means the conversation exists
      mountWidget(embedUrl)
    })
    .catch(function () {
      // Network error – mount anyway so it does not silently break on CORS preflight issues
      mountWidget(embedUrl)
    })

  // ── Widget DOM ───────────────────────────────────────────────────────────────

  function mountWidget(iframeSrc) {
    if (document.getElementById(ROOT_ID)) return // guard against double-init

    var isOpen = false

    // Root wrapper — all inline styles to survive any host page CSS
    var root = el('div', ROOT_ID, {
      position: 'fixed',
      bottom: '24px',
      right: '24px',
      zIndex: '2147483647',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'flex-end',
      gap: '12px',
      fontFamily: 'system-ui, -apple-system, sans-serif',
    })

    // ── iframe panel ──────────────────────────────────────────────────────────

    var panel = el('div', null, {
      width: '380px',
      height: '580px',
      background: '#0b0f1a',
      borderRadius: '16px',
      boxShadow: '0 24px 60px rgba(0,0,0,0.55), 0 0 0 1px rgba(255,255,255,0.1)',
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'column',
      opacity: '0',
      pointerEvents: 'none',
      transform: 'translateY(16px) scale(0.97)',
      transition: 'opacity 0.22s ease, transform 0.22s ease',
    })

    // Thin header bar with title + close button
    var header = el('div', null, {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '10px 14px',
      background: 'rgba(255,255,255,0.04)',
      borderBottom: '1px solid rgba(255,255,255,0.08)',
      flexShrink: '0',
    })

    var brand = el('span', null, {
      fontSize: '13px',
      fontWeight: '600',
      color: '#e2e8f0',
      letterSpacing: '-0.2px',
    })
    brand.textContent = 'ChatRAG'

    var closeBtn = el('button', null, {
      background: 'none',
      border: 'none',
      color: '#64748b',
      cursor: 'pointer',
      padding: '4px',
      display: 'flex',
      alignItems: 'center',
      borderRadius: '6px',
      transition: 'color 0.15s',
    })
    closeBtn.setAttribute('aria-label', 'Close chat')
    closeBtn.innerHTML =
      '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">' +
      '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'
    closeBtn.onmouseover = function () { closeBtn.style.color = '#e2e8f0' }
    closeBtn.onmouseout = function () { closeBtn.style.color = '#64748b' }
    closeBtn.onclick = function () { togglePanel(false) }

    header.appendChild(brand)
    header.appendChild(closeBtn)

    // Iframe
    var iframe = document.createElement('iframe')
    iframe.src = iframeSrc
    iframe.setAttribute('allow', 'microphone; clipboard-write')
    iframe.setAttribute('allowfullscreen', '')
    iframe.setAttribute('title', 'ChatRAG conversation')
    applyStyles(iframe, {
      flex: '1',
      width: '100%',
      border: 'none',
      display: 'block',
      background: '#0b0f1a',
    })

    panel.appendChild(header)
    panel.appendChild(iframe)

    // ── Circle toggle button ──────────────────────────────────────────────────

    var toggle = el('button', null, {
      width: '56px',
      height: '56px',
      borderRadius: '50%',
      background: 'linear-gradient(135deg, #c084fc, #818cf8 50%, #38bdf8)',
      border: 'none',
      cursor: 'pointer',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      boxShadow: '0 4px 20px rgba(129,140,248,0.5)',
      transition: 'transform 0.2s ease, box-shadow 0.2s ease',
      flexShrink: '0',
    })
    toggle.setAttribute('aria-label', 'Open ChatRAG chat')
    toggle.setAttribute('aria-expanded', 'false')

    // ChatRAG icon — chat bubble with RAG nodes, white version
    toggle.innerHTML =
      '<svg width="28" height="28" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">' +
      '<g transform="translate(5,4)">' +
      '<rect x="2" y="2" width="50" height="40" rx="11" ry="11" fill="white" opacity="0.92"/>' +
      '<polygon points="16,42 25,54 32,42" fill="white" opacity="0.92"/>' +
      '<circle cx="17" cy="17" r="5" fill="rgba(11,15,26,0.6)"/>' +
      '<circle cx="37" cy="17" r="5" fill="rgba(11,15,26,0.6)"/>' +
      '<circle cx="27" cy="31" r="5" fill="rgba(11,15,26,0.6)"/>' +
      '<line x1="17" y1="17" x2="37" y2="17" stroke="rgba(11,15,26,0.35)" stroke-width="1.5"/>' +
      '<line x1="17" y1="17" x2="27" y2="31" stroke="rgba(11,15,26,0.35)" stroke-width="1.5"/>' +
      '<line x1="37" y1="17" x2="27" y2="31" stroke="rgba(11,15,26,0.35)" stroke-width="1.5"/>' +
      '<circle cx="17" cy="17" r="2.5" fill="white"/>' +
      '<circle cx="37" cy="17" r="2.5" fill="white"/>' +
      '<circle cx="27" cy="31" r="2.5" fill="white"/>' +
      '</g></svg>'

    toggle.onmouseover = function () {
      toggle.style.transform = 'scale(1.08)'
      toggle.style.boxShadow = '0 6px 28px rgba(129,140,248,0.65)'
    }
    toggle.onmouseout = function () {
      toggle.style.transform = 'scale(1)'
      toggle.style.boxShadow = '0 4px 20px rgba(129,140,248,0.5)'
    }
    toggle.onclick = function () { togglePanel(!isOpen) }

    root.appendChild(panel)
    root.appendChild(toggle)
    document.body.appendChild(root)

    // ── Toggle logic ──────────────────────────────────────────────────────────

    function togglePanel(open) {
      isOpen = open
      if (open) {
        panel.style.opacity = '1'
        panel.style.pointerEvents = 'all'
        panel.style.transform = 'translateY(0) scale(1)'
        toggle.setAttribute('aria-expanded', 'true')
        // Swap icon to X when open
        toggle.innerHTML =
          '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5">' +
          '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'
      } else {
        panel.style.opacity = '0'
        panel.style.pointerEvents = 'none'
        panel.style.transform = 'translateY(16px) scale(0.97)'
        toggle.setAttribute('aria-expanded', 'false')
        // Restore chat icon
        toggle.innerHTML =
          '<svg width="28" height="28" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">' +
          '<g transform="translate(5,4)">' +
          '<rect x="2" y="2" width="50" height="40" rx="11" ry="11" fill="white" opacity="0.92"/>' +
          '<polygon points="16,42 25,54 32,42" fill="white" opacity="0.92"/>' +
          '<circle cx="17" cy="17" r="5" fill="rgba(11,15,26,0.6)"/>' +
          '<circle cx="37" cy="17" r="5" fill="rgba(11,15,26,0.6)"/>' +
          '<circle cx="27" cy="31" r="5" fill="rgba(11,15,26,0.6)"/>' +
          '<line x1="17" y1="17" x2="37" y2="17" stroke="rgba(11,15,26,0.35)" stroke-width="1.5"/>' +
          '<line x1="17" y1="17" x2="27" y2="31" stroke="rgba(11,15,26,0.35)" stroke-width="1.5"/>' +
          '<line x1="37" y1="17" x2="27" y2="31" stroke="rgba(11,15,26,0.35)" stroke-width="1.5"/>' +
          '<circle cx="17" cy="17" r="2.5" fill="white"/>' +
          '<circle cx="37" cy="17" r="2.5" fill="white"/>' +
          '<circle cx="27" cy="31" r="2.5" fill="white"/>' +
          '</g></svg>'
      }
    }

    // Close on Escape key
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && isOpen) togglePanel(false)
    })
  }

  // ── DOM helpers ──────────────────────────────────────────────────────────────

  function el(tag, id, styles) {
    var node = document.createElement(tag)
    if (id) node.id = id
    if (styles) applyStyles(node, styles)
    return node
  }

  function applyStyles(node, styles) {
    Object.assign(node.style, styles)
  }
})()
