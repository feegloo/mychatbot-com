import { onMounted, onBeforeUnmount, watch, type Ref } from 'vue'
import { synthesizeSpeech, synthesizeSpeechWithCaptions, type WordCaption } from '../api'
import { buildSynthesisChunks, cleanTextForTTS, splitIntoSentences } from './useAutoRead'
import {
  type MatchedCaption,
  getLanguageColors,
  extractWordRangesFromRange,
  matchCaptionsToWords,
  alignGhosts,
  ensureHighlightEl,
  ensureGhostEl,
  renderCaptionVisuals,
} from './captionUtils'

const TTS_INSTRUCTIONS_MAX = 4096
const SELECTION_TTS_TEXT_MAX = 4096
const LONG_PRESS_DELAY_MS = 500
const TOUCH_MOVE_THRESHOLD_PX = 5

/**
 * Composable that enables text-to-speech on message content when the
 * conversation language differs from the browser language.
 *
 * Two trigger modes:
 * 1. **Click a word** — click on any word in `.markdown-content` / `.user-text`
 *    to show a speaker icon above it; click the icon to hear pronunciation.
 * 2. **Select text** — drag-select multiple words, speaker appears after 250ms.
 *
 * Visual affordances when active:
 * - Cursor becomes default arrow on translatable content
 * - Hovered words get a subtle brightness boost
 */
export function useTextSelectionSpeech(
  containerRef: Ref<HTMLElement | null>,
  currentLanguage?: Ref<string>,
  welcomeMessage?: Ref<string>,
  messages?: Ref<{ role: string; content: string }[]>,
) {
  const browserLang = navigator.language.split('-')[0]
  // True only for coarse-pointer devices (phones/tablets). Hybrid touchscreen laptops
  // that also have a mouse remain on the mouse/click path.
  const isTouchDevice = window.matchMedia('(hover: none) and (pointer: coarse)').matches
  let tooltip: HTMLDivElement | null = null
  let selectionTimer: ReturnType<typeof setTimeout> | null = null
  let currentAudio: HTMLAudioElement | null = null
  let currentBlobUrl: string | null = null
  let abortController: AbortController | null = null
  let isLoading = false
  let isPlaying = false
  let hideTimer: ReturnType<typeof setTimeout> | null = null
  let highlightEl: HTMLElement | null = null
  let mouseDownPos: { x: number; y: number } | null = null
  let isPinned = false
  let pinnedRange: Range | null = null

  // ── Long-press state (touch devices only) ──
  let longPressTimer: ReturnType<typeof setTimeout> | null = null
  let touchStartPos: { x: number; y: number } | null = null
  /** Set when a long-press successfully pins a word, so the subsequent click event is ignored. */
  let longPressHandled = false

  // ── Caption playback state ──
  let speechRange: Range | null = null
  let captionHighlightEl: HTMLElement | null = null
  let captionGhostEl: HTMLElement | null = null
  let captionAnimFrame: number | null = null
  let activeCaptionWords: MatchedCaption[] | null = null

  /** Is TTS active (current display language differs from browser language)? */
  function isSpeechActive(): boolean {
    const lang = currentLanguage?.value
    if (!lang) return false
    return lang !== browserLang
  }

  /** Toggle .speech-active class on the container */
  function updateSpeechActiveClass() {
    const container = containerRef.value
    if (!container) return
    if (isSpeechActive()) {
      container.classList.add('speech-active')
    } else {
      container.classList.remove('speech-active')
      // If speech just became inactive, clean up any visible tooltip/highlight
      isPinned = false
      pinnedRange = null
      hideTooltipImmediate()
      removeHighlight()
      stopCaptionPlayback()
      stopCurrentAudio()
    }
  }

  /** Hide tooltip immediately without animation (for cleanup when speech deactivated) */
  function hideTooltipImmediate() {
    if (hideTimer) {
      clearTimeout(hideTimer)
      hideTimer = null
    }
    if (tooltip) {
      tooltip.style.display = 'none'
      tooltip.classList.remove('speech-tooltip-visible', 'speech-tooltip-hiding')
    }
  }

  // ── Tooltip ──

  function createTooltipEl(): HTMLDivElement {
    const el = document.createElement('div')
    el.className = 'speech-tooltip'
    el.innerHTML = `<button class="speech-tooltip-btn" title="Listen">
      <svg class="speech-tooltip-icon speech-icon-speaker" focusable="false" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg>
      <svg class="speech-tooltip-icon speech-icon-pause" style="display:none" focusable="false" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
      <svg class="speech-tooltip-spinner" style="display:none" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10" stroke-dasharray="31.4 31.4" stroke-linecap="round"><animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="0.8s" repeatCount="indefinite"/></circle></svg>
    </button>`
    document.body.appendChild(el)
    return el
  }

  function showTooltip(rect: DOMRect, selectedText: string, sourceRange?: Range) {
    speechRange = sourceRange || null
    if (!tooltip) tooltip = createTooltipEl()

    const scrollX = window.scrollX
    const scrollY = window.scrollY
    const tooltipWidth = 34
    const tooltipHeight = 34
    const isMobile = window.matchMedia('(hover: none) and (pointer: coarse)').matches

    let left: number
    let top: number

    if (isMobile) {
      // On mobile: place the icon just below the end of the selected text
      left = rect.right + scrollX - tooltipWidth
      top = rect.bottom + scrollY + 6
      // Keep within viewport horizontally
      if (left + tooltipWidth > scrollX + window.innerWidth - 4) {
        left = scrollX + window.innerWidth - tooltipWidth - 4
      }
      if (left < scrollX + 4) left = scrollX + 4
      // If it clips the bottom, place it above instead
      if (top + tooltipHeight > scrollY + window.innerHeight - 4) {
        top = rect.top + scrollY - tooltipHeight - 6
      }
    } else {
      // Desktop: position to the right of selected text, vertically centered
      left = rect.right + scrollX + 8
      top = rect.top + scrollY + rect.height / 2 - tooltipHeight / 2

      // Fall back to left side if it would clip the right edge
      if (left + tooltipWidth > scrollX + window.innerWidth - 4) {
        left = rect.left + scrollX - tooltipWidth - 8
      }

      if (left < scrollX + 4) left = scrollX + 4
      if (top < scrollY + 4) top = scrollY + 4
      if (top + tooltipHeight > scrollY + window.innerHeight - 4) {
        top = scrollY + window.innerHeight - tooltipHeight - 4
      }
    }

    tooltip.style.left = `${left}px`
    tooltip.style.top = `${top}px`
    // Animate in
    if (hideTimer) {
      clearTimeout(hideTimer)
      hideTimer = null
    }
    tooltip.classList.remove('speech-tooltip-hiding')
    tooltip.style.display = 'block'
    // Force reflow then add visible class for animation
    void tooltip.offsetHeight
    tooltip.classList.add('speech-tooltip-visible')
    setIconState('speaker')

    const btn = tooltip.querySelector('.speech-tooltip-btn') as HTMLButtonElement
    btn.onclick = (e) => {
      e.preventDefault()
      e.stopPropagation()
      if (isPlaying) {
        onStopClick()
      } else {
        onSpeakClick(selectedText)
      }
    }
  }

  function hideTooltip() {
    if (!tooltip) return
    if (tooltip.style.display === 'none') return
    // Animate out
    tooltip.classList.remove('speech-tooltip-visible')
    tooltip.classList.add('speech-tooltip-hiding')
    if (hideTimer) clearTimeout(hideTimer)
    hideTimer = setTimeout(() => {
      if (tooltip) {
        tooltip.style.display = 'none'
        tooltip.classList.remove('speech-tooltip-hiding')
      }
      hideTimer = null
    }, 180) // match CSS transition duration
  }

  function setIconState(state: 'speaker' | 'pause' | 'loading') {
    if (!tooltip) return
    const speaker = tooltip.querySelector('.speech-icon-speaker') as SVGElement
    const pause = tooltip.querySelector('.speech-icon-pause') as SVGElement
    const spinner = tooltip.querySelector('.speech-tooltip-spinner') as SVGElement
    if (speaker) speaker.style.display = state === 'speaker' ? 'block' : 'none'
    if (pause) pause.style.display = state === 'pause' ? 'block' : 'none'
    if (spinner) spinner.style.display = state === 'loading' ? 'block' : 'none'
    isLoading = state === 'loading'
  }

  // ── Audio playback ──

  function stopCurrentAudio() {
    isPlaying = false
    if (currentAudio) {
      currentAudio.pause()
      currentAudio.src = ''
      currentAudio = null
    }
    if (currentBlobUrl) {
      URL.revokeObjectURL(currentBlobUrl)
      currentBlobUrl = null
    }
    if (abortController) {
      abortController.abort()
      abortController = null
    }
  }

  function onStopClick() {
    isPinned = false
    pinnedRange = null
    stopCaptionPlayback()
    stopSingleWordGhost()
    stopCurrentAudio()
    hideTooltip()
    removeHighlight()
  }

  async function onSpeakClick(text: string) {
    stopCaptionPlayback()
    stopCurrentAudio()
    setIconState('loading')
    abortController = new AbortController()
    const signal = abortController.signal

    const resetPlaybackUi = () => {
      isPinned = false
      pinnedRange = null
      stopCaptionPlayback()
      stopSingleWordGhost()
      stopCurrentAudio()
      hideTooltip()
      removeHighlight()
    }

    const playChunkAudio = (blob: Blob): Promise<void> => {
      if (signal.aborted) return Promise.resolve()
      const url = URL.createObjectURL(blob)
      currentBlobUrl = url
      const audio = new Audio(url)
      currentAudio = audio

      return new Promise<void>((resolve) => {
        const cleanup = () => {
          signal.removeEventListener('abort', onAbort)
          if (currentAudio === audio) currentAudio = null
          if (currentBlobUrl === url) {
            URL.revokeObjectURL(url)
            currentBlobUrl = null
          }
          resolve()
        }

        const onAbort = () => {
          audio.pause()
          audio.src = ''
          cleanup()
        }

        signal.addEventListener('abort', onAbort, { once: true })
        audio.addEventListener('ended', cleanup, { once: true })
        audio.addEventListener('error', cleanup, { once: true })
        audio.play().catch(cleanup)
        isPlaying = true
        setIconState('pause')
      })
    }

    try {
      // Build TTS instructions: tone preamble + recent chat context + welcome message
      const welcomeContent = welcomeMessage?.value || ''
      const parts: string[] = [
        'You are a helpful AI assistant reading text aloud. Speak naturally, clearly, and with a warm, friendly tone. ' +
          'Adapt your delivery to the emotional context — be caring, empathetic, supportive, patient, reassuring, ' +
          'encouraging, attentive, compassionate, gentle, understanding, and thoughtful as the content demands.',
      ]

      // Include recent Q&A exchanges (last 3) for emotional context
      const msgs = messages?.value || []
      const recentLines: string[] = []
      let budget = 2000
      for (let i = msgs.length - 1; i >= 0 && budget > 0; i--) {
        const m = msgs[i]
        const label = m.role === 'user' ? 'User asked' : 'Assistant answered'
        const snippet = cleanTextForTTS(m.content).slice(0, 300)
        const line = `${label}: "${snippet}"`
        if (line.length > budget) break
        budget -= line.length
        recentLines.unshift(line)
      }
      if (recentLines.length > 0) {
        parts.push('Recent conversation:\n' + recentLines.join('\n'))
      }

      if (welcomeContent) {
        parts.push(`Document context: ${cleanTextForTTS(welcomeContent).slice(0, 600)}`)
      }

      parts.push(`The user selected this text to hear: "${text.slice(0, 400)}"`)
      const ttsInstructions = parts.join('\n\n').slice(0, TTS_INSTRUCTIONS_MAX)

      const cleaned = cleanTextForTTS(text)
      const truncatedText = cleaned.slice(0, SELECTION_TTS_TEXT_MAX)
      if (cleaned.length > SELECTION_TTS_TEXT_MAX) {
        console.warn('Selection speech truncated to 4096 characters for safe synthesis limits')
      }
      const sentences = splitIntoSentences(truncatedText)
      const chunks = buildSynthesisChunks(sentences)
      if (!chunks.length) {
        resetPlaybackUi()
        return
      }

      const isSingleChunk = chunks.length === 1

      if (isSingleChunk) {
        // Keep caption support for single-chunk synthesis
        const result = await synthesizeSpeechWithCaptions(
          chunks[0],
          currentLanguage?.value,
          browserLang,
          ttsInstructions,
        )
        if (signal.aborted) return

        const isSingleWord = chunks[0].trim().split(/\s+/).length === 1
        if (speechRange && result.captions && result.captions.length > 0) {
          prepareCaptionPlayback(result.captions, result.translatedText)
        }

        const chunkPlayback = playChunkAudio(result.audio)
        if (currentAudio && activeCaptionWords) {
          startCaptionAnimation(currentAudio)
        } else if (currentAudio && isSingleWord && result.translatedText && speechRange) {
          showSingleWordGhost(speechRange, result.translatedText)
        }
        await chunkPlayback
      } else {
        const promises = chunks.map((chunk) =>
          synthesizeSpeech(chunk, currentLanguage?.value, ttsInstructions).catch((error) => {
            console.error('Speech chunk synthesis error:', error)
            return null
          }),
        )
        for (const promise of promises) {
          if (signal.aborted) return
          const blob = await promise
          if (signal.aborted) return
          if (!blob) continue
          await playChunkAudio(blob)
          if (signal.aborted) return
        }
      }

      if (!signal.aborted) resetPlaybackUi()
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      if (signal.aborted) return
      console.error('Speech synthesis error:', err)
      resetPlaybackUi()
    }
  }

  // ── Caption playback functions ──

  /**
   * Prepare caption playback: extract DOM word ranges, match to Whisper captions, align ghosts.
   */
  function prepareCaptionPlayback(captions: WordCaption[], translatedText?: string): void {
    if (!speechRange) return

    const domWords = extractWordRangesFromRange(speechRange)
    if (!domWords.length) return

    const matched = matchCaptionsToWords(captions, domWords)
    if (!matched.length) return

    if (translatedText) {
      alignGhosts(matched, translatedText)
    }

    activeCaptionWords = matched
  }

  /**
   * Start the animation loop that highlights words in sync with audio playback.
   * Each word is shown only during its [start, end) interval; between words the
   * highlight and ghost hide with a CSS transition, then reappear for the next word.
   */
  function startCaptionAnimation(audio: HTMLAudioElement): void {
    let lastIdx = -1

    function tick() {
      if (!activeCaptionWords || !currentAudio) return

      const time = audio.currentTime
      let currentIdx = -1

      // Only highlight while within a word's [start, end) window
      for (let i = 0; i < activeCaptionWords.length; i++) {
        const { caption } = activeCaptionWords[i]
        if (time >= caption.start && time < caption.end) {
          currentIdx = i
          break
        }
      }

      if (currentIdx !== lastIdx) {
        lastIdx = currentIdx
        updateCaptionVisuals(currentIdx)
      }

      captionAnimFrame = requestAnimationFrame(tick)
    }

    captionAnimFrame = requestAnimationFrame(tick)
  }

  /**
   * Update the caption highlight and ghost overlay for the given word index.
   */
  function updateCaptionVisuals(idx: number): void {
    if (!captionHighlightEl) captionHighlightEl = ensureHighlightEl(null)
    if (!captionGhostEl) captionGhostEl = ensureGhostEl(null)
    if (!activeCaptionWords) {
      captionHighlightEl.classList.remove('caption-active')
      captionGhostEl.classList.remove('caption-active')
      return
    }
    const colors = getLanguageColors(currentLanguage?.value || '')
    renderCaptionVisuals(idx, activeCaptionWords, captionHighlightEl, captionGhostEl, colors)
  }

  /**
   * Stop caption playback: cancel animation, hide overlays, clear state.
   */
  function stopCaptionPlayback(): void {
    if (captionAnimFrame !== null) {
      cancelAnimationFrame(captionAnimFrame)
      captionAnimFrame = null
    }
    activeCaptionWords = null
    speechRange = null
    if (captionHighlightEl) captionHighlightEl.classList.remove('caption-active')
    if (captionGhostEl) captionGhostEl.classList.remove('caption-active')
  }

  /**
   * Show a static ghost translation + highlight for a single-word TTS
   * (no Whisper timestamps needed — just display while audio plays).
   */
  function showSingleWordGhost(range: Range, translatedText: string): void {
    const rect = range.getBoundingClientRect()
    if (rect.width === 0 && rect.height === 0) return
    const colors = getLanguageColors(currentLanguage?.value || '')
    if (!captionHighlightEl) captionHighlightEl = ensureHighlightEl(null)
    if (!captionGhostEl) captionGhostEl = ensureGhostEl(null)
    const singleWordMatched: MatchedCaption[] = [
      {
        caption: { word: translatedText.trim(), start: 0, end: 9999 },
        range,
        ghostWord: translatedText.trim(),
      },
    ]
    renderCaptionVisuals(0, singleWordMatched, captionHighlightEl, captionGhostEl, colors)
  }

  function stopSingleWordGhost(): void {
    if (captionHighlightEl) captionHighlightEl.classList.remove('caption-active')
    if (captionGhostEl) captionGhostEl.classList.remove('caption-active')
  }

  // ── Word highlight on hover ──

  function removeHighlight() {
    if (highlightEl && highlightEl.parentNode) {
      highlightEl.remove()
    }
    highlightEl = null
  }

  function isInContent(el: HTMLElement | null): boolean {
    if (!el) return false
    return !!(el.closest('.markdown-content') || el.closest('.user-text'))
  }

  /**
   * Checklist items render as `<li>` containing a `.checklist-box` span.
   * Clicking a word inside such an item should NOT trigger the speaker
   * tooltip (the whole line is meant to act as a clickable checkbox).
   * Text-selection inside a checklist item still shows the speaker.
   */
  function isInChecklistItem(el: HTMLElement | null): boolean {
    if (!el) return false
    const li = el.closest('li')
    return !!(li && li.querySelector(':scope > .checklist-box'))
  }

  /**
   * Given a point (clientX, clientY) inside a text node, return a Range
   * spanning the word at that position.
   */
  function getWordRangeAtPoint(x: number, y: number): Range | null {
    let range: Range | null = null

    // caretRangeFromPoint (Chrome, Safari) / caretPositionFromPoint (Firefox)
    if (document.caretRangeFromPoint) {
      range = document.caretRangeFromPoint(x, y)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } else if ((document as any).caretPositionFromPoint) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const pos = (document as any).caretPositionFromPoint(x, y)
      if (pos && pos.offsetNode) {
        range = document.createRange()
        range.setStart(pos.offsetNode, pos.offset)
        range.collapse(true)
      }
    }
    if (!range) return null

    const node = range.startContainer
    if (node.nodeType !== Node.TEXT_NODE) return null

    const text = node.textContent || ''
    const offset = range.startOffset

    // Find word boundaries (letters, digits, hyphens, apostrophes, unicode letters)
    const wordChars = /[\p{L}\p{N}'\u2019-]/u

    let start = offset
    while (start > 0 && wordChars.test(text[start - 1])) start--

    let end = offset
    while (end < text.length && wordChars.test(text[end])) end++

    if (start === end) return null

    const wordRange = document.createRange()
    wordRange.setStart(node, start)
    wordRange.setEnd(node, end)

    // Verify the cursor is actually over the word, not in nearby whitespace/padding.
    // caretRangeFromPoint snaps to the nearest text even when cursor is in empty space.
    const rect = wordRange.getBoundingClientRect()
    const pad = 4 // small tolerance in px
    if (
      x < rect.left - pad ||
      x > rect.right + pad ||
      y < rect.top - pad ||
      y > rect.bottom + pad
    ) {
      return null
    }

    return wordRange
  }

  function onMouseMove(e: MouseEvent) {
    if (!isSpeechActive()) {
      removeHighlight()
      return
    }
    if (isPlaying || isPinned) return

    const container = containerRef.value
    if (!container) return

    const target = e.target as HTMLElement
    if (!container.contains(target)) {
      removeHighlight()
      return
    }
    if (!isInContent(target)) {
      removeHighlight()
      return
    }
    // Skip interactive elements (action buttons, links, etc.) — same as onClickWord
    if (target.closest('button, a, .inline-source-btn, .action-btn, .checklist-box')) {
      removeHighlight()
      return
    }
    // Skip checklist items — whole line acts as a checkbox toggle
    if (isInChecklistItem(target)) {
      removeHighlight()
      return
    }

    // Don't highlight while text is being selected
    const sel = window.getSelection()
    if (sel && !sel.isCollapsed) {
      removeHighlight()
      return
    }

    const wordRange = getWordRangeAtPoint(e.clientX, e.clientY)
    if (!wordRange) {
      removeHighlight()
      return
    }

    const word = wordRange.toString().trim()
    if (word.length < 2) {
      removeHighlight()
      return
    }

    // Position a highlight overlay on top of the word
    const rect = wordRange.getBoundingClientRect()

    if (!highlightEl) {
      highlightEl = document.createElement('div')
      highlightEl.className = 'speech-word-highlight'
      document.body.appendChild(highlightEl)
    }

    const scrollX = window.scrollX
    const scrollY = window.scrollY
    highlightEl.style.left = `${rect.left + scrollX - 2}px`
    highlightEl.style.top = `${rect.top + scrollY - 1}px`
    highlightEl.style.width = `${rect.width + 4}px`
    highlightEl.style.height = `${rect.height + 2}px`
    highlightEl.style.display = 'block'
  }

  // ── Click to select word ──

  function onMouseDown(e: MouseEvent) {
    // If clicking on the tooltip itself, don't hide
    if (tooltip && tooltip.contains(e.target as Node)) return
    // Always track down-position so click-vs-drag detection works while audio is playing.
    mouseDownPos = { x: e.clientX, y: e.clientY }

    // Keep current playback/loader tooltip visible.
    if (isLoading || isPlaying) return

    // Don't hide tooltip when pinned — onClickWord will handle toggling.
    if (!isPinned) hideTooltip()
  }

  function unpinWord() {
    isPinned = false
    pinnedRange = null
    hideTooltip()
    removeHighlight()
  }

  // ── Long-press (touch devices) ──

  function onTouchStart(e: TouchEvent) {
    // Cancel any in-flight long-press (e.g. second finger placed = pinch/zoom)
    if (longPressTimer) {
      clearTimeout(longPressTimer)
      longPressTimer = null
    }
    touchStartPos = null

    if (!isSpeechActive()) return
    if (e.touches.length !== 1) return

    const target = e.target as HTMLElement | null
    const container = containerRef.value
    if (!target || !container || !container.contains(target)) return
    if (!isInContent(target)) return
    // Don't interfere with interactive elements or checklist items
    if (target.closest('button, a, .inline-source-btn, .action-btn, .checklist-box')) return
    if (isInChecklistItem(target)) return

    const touch = e.touches[0]
    touchStartPos = { x: touch.clientX, y: touch.clientY }
    longPressHandled = false

    longPressTimer = setTimeout(() => {
      longPressTimer = null
      if (!touchStartPos) return

      const { x, y } = touchStartPos
      pinWordAt(x, y)
      if (isPinned) {
        // Prevent the subsequent click from immediately un-pinning the word
        longPressHandled = true
      }
    }, LONG_PRESS_DELAY_MS)
  }

  function onTouchMove(e: TouchEvent) {
    if (!longPressTimer) return
    const touch = e.touches[0]
    if (!touchStartPos) return
    const dx = Math.abs(touch.clientX - touchStartPos.x)
    const dy = Math.abs(touch.clientY - touchStartPos.y)
    if (dx > TOUCH_MOVE_THRESHOLD_PX || dy > TOUCH_MOVE_THRESHOLD_PX) {
      clearTimeout(longPressTimer)
      longPressTimer = null
    }
  }

  function onTouchEnd() {
    if (longPressTimer) {
      clearTimeout(longPressTimer)
      longPressTimer = null
    }
    touchStartPos = null
  }

  /**
   * Pin the word at the given viewport coordinates.
   * Shared by long-press (touch) and click (mouse) paths.
   */
  function pinWordAt(x: number, y: number) {
    const container = containerRef.value
    if (!container) return

    const wordRange = getWordRangeAtPoint(x, y)
    if (!wordRange) {
      if (isPinned) unpinWord()
      return
    }

    const word = wordRange.toString().trim()
    if (word.length < 2) {
      if (isPinned) unpinWord()
      return
    }

    const rect = wordRange.getBoundingClientRect()
    if (rect.width === 0 && rect.height === 0) return

    // If tapping the same pinned word, toggle off
    if (
      isPinned &&
      pinnedRange &&
      pinnedRange.startContainer === wordRange.startContainer &&
      pinnedRange.startOffset === wordRange.startOffset &&
      pinnedRange.endOffset === wordRange.endOffset
    ) {
      unpinWord()
      return
    }

    isPinned = true
    pinnedRange = wordRange
    showTooltip(rect, word, wordRange)
  }

  function onClickWord(e: MouseEvent) {
    if (!isSpeechActive()) return

    // On touch devices the speaker is shown via long-press, not single tap.
    if (isTouchDevice) {
      if (longPressHandled) {
        longPressHandled = false
      }
      return
    }

    // If clicking the tooltip, ignore
    if (tooltip && tooltip.contains(e.target as Node)) return

    // Only treat as a word-click if the mouse didn't move far (not a drag-select)
    if (mouseDownPos) {
      const dx = Math.abs(e.clientX - mouseDownPos.x)
      const dy = Math.abs(e.clientY - mouseDownPos.y)
      if (dx > 5 || dy > 5) return // was a drag/selection, let selectionchange handle it
    }

    const container = containerRef.value
    if (!container) return

    const target = e.target as HTMLElement
    if (!container.contains(target) || !isInContent(target)) {
      if (isPinned) unpinWord()
      return
    }

    // Don't interfere with interactive elements
    if (target.closest('button, a, .inline-source-btn, .action-btn, .checklist-box')) return

    // Skip checklist items — clicking a word inside a rich checklist should
    // toggle the checkbox (handled elsewhere), not open the speaker tooltip.
    // Text selection inside checklists still shows the tooltip via onSelectionChange.
    if (isInChecklistItem(target)) {
      if (isPinned) unpinWord()
      return
    }

    // If there's already a text selection, let the selection handler take care of it
    const sel = window.getSelection()
    if (sel && !sel.isCollapsed && sel.toString().trim().length > 1) return

    pinWordAt(e.clientX, e.clientY)
  }

  // ── Text selection ──

  function onSelectionChange() {
    if (selectionTimer) {
      clearTimeout(selectionTimer)
      selectionTimer = null
    }

    const selection = window.getSelection()
    if (!selection || selection.isCollapsed || !selection.toString().trim()) {
      // Don't hide if tooltip is showing for a word-click
      return
    }

    if (!isSpeechActive()) return

    const container = containerRef.value
    if (!container) return

    const anchorNode = selection.anchorNode
    const focusNode = selection.focusNode
    if (!anchorNode || !focusNode) return
    if (!container.contains(anchorNode) || !container.contains(focusNode)) return

    const anchorEl =
      anchorNode.nodeType === Node.ELEMENT_NODE
        ? (anchorNode as HTMLElement)
        : anchorNode.parentElement
    if (!anchorEl || !isInContent(anchorEl)) return

    selectionTimer = setTimeout(() => {
      const sel = window.getSelection()
      if (!sel || sel.isCollapsed || !sel.toString().trim()) return

      const text = sel.toString().trim()
      if (text.length < 2) return

      try {
        const range = sel.getRangeAt(0)
        const rect = range.getBoundingClientRect()
        if (rect.width === 0 && rect.height === 0) return
        showTooltip(rect, text, range)
      } catch {
        /* ignore */
      }
    }, 250)
  }

  function onScroll() {
    if (!isPlaying && !isPinned) hideTooltip()
    if (!isPinned) removeHighlight()
  }

  function onMouseLeave() {
    if (!isPinned) removeHighlight()
  }

  // ── Lifecycle ──

  // Watch currentLanguage to toggle .speech-active class
  if (currentLanguage) {
    watch(currentLanguage, updateSpeechActiveClass, { immediate: true })
  }

  onMounted(() => {
    updateSpeechActiveClass()
    document.addEventListener('selectionchange', onSelectionChange)
    document.addEventListener('mousedown', onMouseDown)
    document.addEventListener('click', onClickWord)
    document.addEventListener('mousemove', onMouseMove)
    window.addEventListener('scroll', onScroll, true)
    containerRef.value?.addEventListener('mouseleave', onMouseLeave)
    if (isTouchDevice) {
      document.addEventListener('touchstart', onTouchStart, { passive: true })
      document.addEventListener('touchmove', onTouchMove, { passive: true })
      document.addEventListener('touchend', onTouchEnd)
      document.addEventListener('touchcancel', onTouchEnd)
    }
  })

  onBeforeUnmount(() => {
    if (selectionTimer) clearTimeout(selectionTimer)
    if (longPressTimer) clearTimeout(longPressTimer)
    document.removeEventListener('selectionchange', onSelectionChange)
    document.removeEventListener('mousedown', onMouseDown)
    document.removeEventListener('click', onClickWord)
    document.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('scroll', onScroll, true)
    containerRef.value?.removeEventListener('mouseleave', onMouseLeave)
    if (isTouchDevice) {
      document.removeEventListener('touchstart', onTouchStart)
      document.removeEventListener('touchmove', onTouchMove)
      document.removeEventListener('touchend', onTouchEnd)
      document.removeEventListener('touchcancel', onTouchEnd)
    }
    stopCaptionPlayback()
    stopCurrentAudio()
    removeHighlight()
    if (tooltip) {
      tooltip.remove()
      tooltip = null
    }
    if (captionHighlightEl) {
      captionHighlightEl.remove()
      captionHighlightEl = null
    }
    if (captionGhostEl) {
      captionGhostEl.remove()
      captionGhostEl = null
    }
    containerRef.value?.classList.remove('speech-active')
  })
}
