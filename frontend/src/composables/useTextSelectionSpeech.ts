import { onMounted, onBeforeUnmount, watch, type Ref } from "vue";
import { synthesizeSpeech } from "../api";

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
) {
  const browserLang = navigator.language.split("-")[0];
  let tooltip: HTMLDivElement | null = null;
  let selectionTimer: ReturnType<typeof setTimeout> | null = null;
  let currentAudio: HTMLAudioElement | null = null;
  let currentBlobUrl: string | null = null;
  let abortController: AbortController | null = null;
  let isLoading = false;
  let isPlaying = false;
  let hideTimer: ReturnType<typeof setTimeout> | null = null;
  let highlightEl: HTMLElement | null = null;
  let lastWordRange: Range | null = null;
  let mouseDownPos: { x: number; y: number } | null = null;

  /** Is TTS active (current display language differs from browser language)? */
  function isSpeechActive(): boolean {
    const lang = currentLanguage?.value;
    if (!lang) return false;
    return lang !== browserLang;
  }

  /** Toggle .speech-active class on the container */
  function updateSpeechActiveClass() {
    const container = containerRef.value;
    if (!container) return;
    if (isSpeechActive()) {
      container.classList.add("speech-active");
    } else {
      container.classList.remove("speech-active");
      // If speech just became inactive, clean up any visible tooltip/highlight
      hideTooltipImmediate();
      removeHighlight();
      stopCurrentAudio();
    }
  }

  /** Hide tooltip immediately without animation (for cleanup when speech deactivated) */
  function hideTooltipImmediate() {
    if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
    if (tooltip) {
      tooltip.style.display = "none";
      tooltip.classList.remove("speech-tooltip-visible", "speech-tooltip-hiding");
    }
  }

  // ── Tooltip ──

  function createTooltipEl(): HTMLDivElement {
    const el = document.createElement("div");
    el.className = "speech-tooltip";
    el.innerHTML = `<button class="speech-tooltip-btn" title="Listen">
      <svg class="speech-tooltip-icon speech-icon-speaker" focusable="false" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg>
      <svg class="speech-tooltip-icon speech-icon-pause" style="display:none" focusable="false" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
      <svg class="speech-tooltip-spinner" style="display:none" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10" stroke-dasharray="31.4 31.4" stroke-linecap="round"><animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="0.8s" repeatCount="indefinite"/></circle></svg>
    </button>`;
    document.body.appendChild(el);
    return el;
  }

  function showTooltip(rect: DOMRect, selectedText: string) {
    if (!tooltip) tooltip = createTooltipEl();

    const scrollX = window.scrollX;
    const scrollY = window.scrollY;
    const tooltipWidth = 34;
    const tooltipHeight = 34;
    let left = rect.left + scrollX + rect.width / 2 - tooltipWidth / 2;
    let top = rect.top + scrollY - tooltipHeight - 8;

    if (left < scrollX + 4) left = scrollX + 4;
    if (left + tooltipWidth > scrollX + window.innerWidth - 4) {
      left = scrollX + window.innerWidth - tooltipWidth - 4;
    }
    if (top < scrollY + 4) {
      top = rect.bottom + scrollY + 8;
    }

    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
    // Animate in
    if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
    tooltip.classList.remove("speech-tooltip-hiding");
    tooltip.style.display = "block";
    // Force reflow then add visible class for animation
    void tooltip.offsetHeight;
    tooltip.classList.add("speech-tooltip-visible");
    setIconState("speaker");

    const btn = tooltip.querySelector(".speech-tooltip-btn") as HTMLButtonElement;
    btn.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (isPlaying) {
        onStopClick();
      } else {
        onSpeakClick(selectedText);
      }
    };
  }

  function hideTooltip() {
    if (!tooltip) return;
    if (tooltip.style.display === "none") return;
    // Animate out
    tooltip.classList.remove("speech-tooltip-visible");
    tooltip.classList.add("speech-tooltip-hiding");
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      if (tooltip) {
        tooltip.style.display = "none";
        tooltip.classList.remove("speech-tooltip-hiding");
      }
      hideTimer = null;
    }, 180); // match CSS transition duration
  }

  function setIconState(state: "speaker" | "pause" | "loading") {
    if (!tooltip) return;
    const speaker = tooltip.querySelector(".speech-icon-speaker") as SVGElement;
    const pause = tooltip.querySelector(".speech-icon-pause") as SVGElement;
    const spinner = tooltip.querySelector(".speech-tooltip-spinner") as SVGElement;
    if (speaker) speaker.style.display = state === "speaker" ? "block" : "none";
    if (pause) pause.style.display = state === "pause" ? "block" : "none";
    if (spinner) spinner.style.display = state === "loading" ? "block" : "none";
    isLoading = state === "loading";
  }

  // ── Audio playback ──

  function stopCurrentAudio() {
    isPlaying = false;
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.src = "";
      currentAudio = null;
    }
    if (currentBlobUrl) {
      URL.revokeObjectURL(currentBlobUrl);
      currentBlobUrl = null;
    }
    if (abortController) {
      abortController.abort();
      abortController = null;
    }
  }

  function onStopClick() {
    stopCurrentAudio();
    hideTooltip();
  }

  async function onSpeakClick(text: string) {
    stopCurrentAudio();
    setIconState("loading");
    abortController = new AbortController();

    try {
      const blob = await synthesizeSpeech(text.slice(0, 2000), currentLanguage?.value);
      if (abortController?.signal.aborted) return;

      const url = URL.createObjectURL(blob);
      currentBlobUrl = url;

      const audio = new Audio(url);
      currentAudio = audio;

      audio.addEventListener("ended", () => {
        stopCurrentAudio();
        hideTooltip();
      });
      audio.addEventListener("error", () => {
        stopCurrentAudio();
        hideTooltip();
      });

      await audio.play();
      isPlaying = true;
      // Show pause icon while playing
      setIconState("pause");
    } catch (err: any) {
      if (err?.name === "AbortError" || abortController?.signal.aborted) return;
      console.error("Speech synthesis error:", err);
      hideTooltip();
    }
  }

  // ── Word highlight on hover ──

  function removeHighlight() {
    if (highlightEl && highlightEl.parentNode) {
      highlightEl.remove();
    }
    highlightEl = null;
  }

  function isInContent(el: HTMLElement | null): boolean {
    if (!el) return false;
    return !!(el.closest(".markdown-content") || el.closest(".user-text"));
  }

  /**
   * Given a point (clientX, clientY) inside a text node, return a Range
   * spanning the word at that position.
   */
  function getWordRangeAtPoint(x: number, y: number): Range | null {
    let range: Range | null = null;

    // caretRangeFromPoint (Chrome, Safari) / caretPositionFromPoint (Firefox)
    if (document.caretRangeFromPoint) {
      range = document.caretRangeFromPoint(x, y);
    } else if ((document as any).caretPositionFromPoint) {
      const pos = (document as any).caretPositionFromPoint(x, y);
      if (pos && pos.offsetNode) {
        range = document.createRange();
        range.setStart(pos.offsetNode, pos.offset);
        range.collapse(true);
      }
    }
    if (!range) return null;

    const node = range.startContainer;
    if (node.nodeType !== Node.TEXT_NODE) return null;

    const text = node.textContent || "";
    const offset = range.startOffset;

    // Find word boundaries (letters, digits, hyphens, apostrophes, unicode letters)
    const wordChars = /[\p{L}\p{N}'\u2019-]/u;

    let start = offset;
    while (start > 0 && wordChars.test(text[start - 1])) start--;

    let end = offset;
    while (end < text.length && wordChars.test(text[end])) end++;

    if (start === end) return null;

    const wordRange = document.createRange();
    wordRange.setStart(node, start);
    wordRange.setEnd(node, end);

    // Verify the cursor is actually over the word, not in nearby whitespace/padding.
    // caretRangeFromPoint snaps to the nearest text even when cursor is in empty space.
    const rect = wordRange.getBoundingClientRect();
    const pad = 4; // small tolerance in px
    if (x < rect.left - pad || x > rect.right + pad || y < rect.top - pad || y > rect.bottom + pad) {
      return null;
    }

    return wordRange;
  }

  function onMouseMove(e: MouseEvent) {
    if (!isSpeechActive()) { removeHighlight(); return; }

    const container = containerRef.value;
    if (!container) return;

    const target = e.target as HTMLElement;
    if (!container.contains(target)) { removeHighlight(); return; }
    if (!isInContent(target)) { removeHighlight(); return; }

    // Don't highlight while text is being selected
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed) { removeHighlight(); return; }

    const wordRange = getWordRangeAtPoint(e.clientX, e.clientY);
    if (!wordRange) { removeHighlight(); return; }

    const word = wordRange.toString().trim();
    if (word.length < 2) { removeHighlight(); return; }

    // Position a highlight overlay on top of the word
    const rect = wordRange.getBoundingClientRect();
    lastWordRange = wordRange;

    if (!highlightEl) {
      highlightEl = document.createElement("div");
      highlightEl.className = "speech-word-highlight";
      document.body.appendChild(highlightEl);
    }

    const scrollX = window.scrollX;
    const scrollY = window.scrollY;
    highlightEl.style.left = `${rect.left + scrollX - 2}px`;
    highlightEl.style.top = `${rect.top + scrollY - 1}px`;
    highlightEl.style.width = `${rect.width + 4}px`;
    highlightEl.style.height = `${rect.height + 2}px`;
    highlightEl.style.display = "block";
  }

  // ── Click to select word ──

  function onMouseDown(e: MouseEvent) {
    // If clicking on the tooltip itself, don't hide
    if (tooltip && tooltip.contains(e.target as Node)) return;
    // Don't hide while loading or playing
    if (isLoading || isPlaying) return;
    hideTooltip();
    mouseDownPos = { x: e.clientX, y: e.clientY };
  }

  function onClickWord(e: MouseEvent) {
    if (!isSpeechActive()) return;

    // If clicking the tooltip, ignore
    if (tooltip && tooltip.contains(e.target as Node)) return;

    // Only treat as a word-click if the mouse didn't move far (not a drag-select)
    if (mouseDownPos) {
      const dx = Math.abs(e.clientX - mouseDownPos.x);
      const dy = Math.abs(e.clientY - mouseDownPos.y);
      if (dx > 5 || dy > 5) return; // was a drag/selection, let selectionchange handle it
    }

    const container = containerRef.value;
    if (!container) return;

    const target = e.target as HTMLElement;
    if (!container.contains(target)) return;
    if (!isInContent(target)) return;

    // Don't interfere with interactive elements
    if (target.closest("button, a, .inline-source-btn, .action-btn, .checklist-box")) return;

    // If there's already a text selection, let the selection handler take care of it
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed && sel.toString().trim().length > 1) return;

    const wordRange = getWordRangeAtPoint(e.clientX, e.clientY);
    if (!wordRange) return;

    const word = wordRange.toString().trim();
    if (word.length < 2) return;

    const rect = wordRange.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return;

    showTooltip(rect, word);
  }

  // ── Text selection ──

  function onSelectionChange() {
    if (selectionTimer) { clearTimeout(selectionTimer); selectionTimer = null; }

    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || !selection.toString().trim()) {
      // Don't hide if tooltip is showing for a word-click
      return;
    }

    if (!isSpeechActive()) return;

    const container = containerRef.value;
    if (!container) return;

    const anchorNode = selection.anchorNode;
    const focusNode = selection.focusNode;
    if (!anchorNode || !focusNode) return;
    if (!container.contains(anchorNode) || !container.contains(focusNode)) return;

    const anchorEl = anchorNode.nodeType === Node.ELEMENT_NODE
      ? anchorNode as HTMLElement
      : anchorNode.parentElement;
    if (!anchorEl || !isInContent(anchorEl)) return;

    selectionTimer = setTimeout(() => {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed || !sel.toString().trim()) return;

      const text = sel.toString().trim();
      if (text.length < 2) return;

      try {
        const range = sel.getRangeAt(0);
        const rect = range.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) return;
        showTooltip(rect, text);
      } catch { /* ignore */ }
    }, 250);
  }

  function onScroll() {
    hideTooltip();
    removeHighlight();
  }

  function onMouseLeave() {
    removeHighlight();
  }

  // ── Lifecycle ──

  // Watch currentLanguage to toggle .speech-active class
  if (currentLanguage) {
    watch(currentLanguage, updateSpeechActiveClass, { immediate: true });
  }

  onMounted(() => {
    updateSpeechActiveClass();
    document.addEventListener("selectionchange", onSelectionChange);
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("click", onClickWord);
    document.addEventListener("mousemove", onMouseMove);
    window.addEventListener("scroll", onScroll, true);
    containerRef.value?.addEventListener("mouseleave", onMouseLeave);
  });

  onBeforeUnmount(() => {
    if (selectionTimer) clearTimeout(selectionTimer);
    document.removeEventListener("selectionchange", onSelectionChange);
    document.removeEventListener("mousedown", onMouseDown);
    document.removeEventListener("click", onClickWord);
    document.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("scroll", onScroll, true);
    containerRef.value?.removeEventListener("mouseleave", onMouseLeave);
    stopCurrentAudio();
    removeHighlight();
    if (tooltip) { tooltip.remove(); tooltip = null; }
    containerRef.value?.classList.remove("speech-active");
  });
}
