// ChatRAG Extension — Content Script
// Injects the chat widget into the current page

const WIDGET_ID = '__chatrag_widget__'
const CHATRAG_BASE = 'https://chatrag.app'

// ── Message listener ──────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message) => {
  if (message.type === 'SHOW_WIDGET') {
    createWidget(message.conversationId, true)
  }
  if (message.type === 'OPEN_WIDGET') {
    const existing = document.getElementById(WIDGET_ID)
    if (existing) {
      openPanel()
    } else {
      createWidget(message.conversationId, true)
    }
  }
})

// ── Widget state ──────────────────────────────────────────────────────────────

let panelOpen = false

function openPanel() {
  const panel = document.getElementById('__chatrag_panel__')
  const toggle = document.getElementById('__chatrag_toggle__')
  if (!panel || !toggle) return
  panelOpen = true
  panel.style.opacity = '1'
  panel.style.pointerEvents = 'all'
  panel.style.transform = 'translateY(0) scale(1)'
  toggle.setAttribute('aria-expanded', 'true')
}

function closePanel() {
  const panel = document.getElementById('__chatrag_panel__')
  const toggle = document.getElementById('__chatrag_toggle__')
  if (!panel || !toggle) return
  panelOpen = false
  panel.style.opacity = '0'
  panel.style.pointerEvents = 'none'
  panel.style.transform = 'translateY(16px) scale(0.97)'
  toggle.setAttribute('aria-expanded', 'false')
}

function togglePanel() {
  if (panelOpen) closePanel()
  else openPanel()
}

// ── Widget creation ───────────────────────────────────────────────────────────

function createWidget(conversationId, openImmediately = false) {
  // Remove any existing widget first
  const existing = document.getElementById(WIDGET_ID)
  if (existing) existing.remove()

  const embedUrl = `${CHATRAG_BASE}/c/${conversationId}?embed=1`

  // Root container — uses inline styles to avoid page CSS conflicts
  const root = document.createElement('div')
  root.id = WIDGET_ID
  applyStyles(root, {
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

  // ── Chat panel ──
  const panel = document.createElement('div')
  panel.id = '__chatrag_panel__'
  applyStyles(panel, {
    width: '400px',
    height: '580px',
    background: '#0b0f1a',
    borderRadius: '16px',
    boxShadow: '0 24px 60px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.1)',
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
    opacity: '0',
    pointerEvents: 'none',
    transform: 'translateY(16px) scale(0.97)',
    transition: 'opacity 0.2s ease, transform 0.2s ease',
  })

  // Panel header bar
  const header = document.createElement('div')
  applyStyles(header, {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 14px',
    background: 'rgba(255,255,255,0.04)',
    borderBottom: '1px solid rgba(255,255,255,0.08)',
    flexShrink: '0',
  })

  // Logo + title
  const branding = document.createElement('div')
  applyStyles(branding, { display: 'flex', alignItems: 'center', gap: '8px' })

  const logoSvg = createLogoSvg(20)
  const brandName = document.createElement('span')
  applyStyles(brandName, {
    fontSize: '13px',
    fontWeight: '600',
    color: '#e2e8f0',
    letterSpacing: '-0.1px',
  })
  brandName.textContent = 'ChatRAG'
  branding.appendChild(logoSvg)
  branding.appendChild(brandName)

  // Close button
  const closeBtn = document.createElement('button')
  applyStyles(closeBtn, {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '28px',
    height: '28px',
    background: 'transparent',
    border: 'none',
    borderRadius: '6px',
    color: '#64748b',
    cursor: 'pointer',
    transition: 'background 0.15s, color 0.15s',
    padding: '0',
  })
  closeBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`
  closeBtn.title = 'Close chat'
  closeBtn.addEventListener('mouseover', () => {
    closeBtn.style.background = 'rgba(255,255,255,0.08)'
    closeBtn.style.color = '#e2e8f0'
  })
  closeBtn.addEventListener('mouseout', () => {
    closeBtn.style.background = 'transparent'
    closeBtn.style.color = '#64748b'
  })
  closeBtn.addEventListener('click', closePanel)

  header.appendChild(branding)
  header.appendChild(closeBtn)

  // Iframe
  const iframe = document.createElement('iframe')
  iframe.src = embedUrl
  applyStyles(iframe, {
    flex: '1',
    width: '100%',
    border: 'none',
    background: '#0b0f1a',
  })
  iframe.setAttribute('allow', 'clipboard-write')
  iframe.setAttribute('title', 'ChatRAG conversation')

  panel.appendChild(header)
  panel.appendChild(iframe)

  // ── Toggle button (floating circle) ──
  const toggle = document.createElement('button')
  toggle.id = '__chatrag_toggle__'
  toggle.setAttribute('aria-label', 'Toggle ChatRAG chat')
  toggle.setAttribute('aria-expanded', 'false')
  applyStyles(toggle, {
    width: '56px',
    height: '56px',
    borderRadius: '50%',
    background: 'linear-gradient(135deg, #7C3AED, #5B21B6)',
    border: 'none',
    cursor: 'pointer',
    boxShadow: '0 4px 20px rgba(124,58,237,0.5)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'transform 0.2s ease, box-shadow 0.2s ease',
    padding: '0',
    flexShrink: '0',
  })
  toggle.innerHTML = createLogoSvg(26).outerHTML

  toggle.addEventListener('mouseover', () => {
    toggle.style.transform = 'scale(1.08)'
    toggle.style.boxShadow = '0 6px 28px rgba(124,58,237,0.65)'
  })
  toggle.addEventListener('mouseout', () => {
    toggle.style.transform = 'scale(1)'
    toggle.style.boxShadow = '0 4px 20px rgba(124,58,237,0.5)'
  })
  toggle.addEventListener('click', togglePanel)

  root.appendChild(panel)
  root.appendChild(toggle)
  document.body.appendChild(root)

  if (openImmediately) {
    // Small delay so the transition plays on first open
    requestAnimationFrame(() => requestAnimationFrame(() => openPanel()))
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function applyStyles(el, styles) {
  Object.assign(el.style, styles)
}

function createLogoSvg(size) {
  const ns = 'http://www.w3.org/2000/svg'
  const svg = document.createElementNS(ns, 'svg')
  svg.setAttribute('width', String(size))
  svg.setAttribute('height', String(size))
  svg.setAttribute('viewBox', '0 0 32 32')
  svg.setAttribute('fill', 'none')

  const defs = document.createElementNS(ns, 'defs')
  const grad = document.createElementNS(ns, 'linearGradient')
  grad.setAttribute('id', '__chatrag_grad__')
  grad.setAttribute('x1', '0')
  grad.setAttribute('y1', '0')
  grad.setAttribute('x2', '0')
  grad.setAttribute('y2', '32')
  grad.setAttribute('gradientUnits', 'userSpaceOnUse')
  const stop1 = document.createElementNS(ns, 'stop')
  stop1.setAttribute('offset', '0%')
  stop1.setAttribute('stop-color', '#7C3AED')
  const stop2 = document.createElementNS(ns, 'stop')
  stop2.setAttribute('offset', '100%')
  stop2.setAttribute('stop-color', '#5B21B6')
  grad.appendChild(stop1)
  grad.appendChild(stop2)
  defs.appendChild(grad)

  const rect = document.createElementNS(ns, 'rect')
  rect.setAttribute('width', '32')
  rect.setAttribute('height', '32')
  rect.setAttribute('rx', '8')
  rect.setAttribute('fill', 'url(#__chatrag_grad__)')

  const text = document.createElementNS(ns, 'text')
  text.setAttribute('x', '16')
  text.setAttribute('y', '22')
  text.setAttribute('text-anchor', 'middle')
  text.setAttribute('fill', 'white')
  text.setAttribute('font-family', "system-ui,Arial,sans-serif")
  text.setAttribute('font-weight', '700')
  text.setAttribute('font-size', '13')
  text.textContent = 'CR'

  svg.appendChild(defs)
  svg.appendChild(rect)
  svg.appendChild(text)
  return svg
}
