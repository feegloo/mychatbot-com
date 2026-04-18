<template>
  <div ref="rootEl" class="pdf-page-viewer" @wheel.passive="onWheel">
    <div v-if="loading" class="pdf-page-loading">Loading…</div>
    <div v-if="error" class="pdf-page-error">{{ error }}</div>
    <div
      ref="pagesContainer"
      v-show="!loading && !error"
      class="pdf-pages-container"
    >
      <div
        v-for="pg in renderedPages"
        :key="pg"
        :ref="el => setPageRef(pg, el as HTMLElement)"
        class="pdf-page-wrapper"
        :data-page="pg"
      >
        <canvas :ref="el => setCanvasRef(pg, el as HTMLCanvasElement)" class="pdf-page-canvas" />
        <div :ref="el => setTextRef(pg, el as HTMLElement)" class="textLayer" />
      </div>
    </div>
    <!-- Toolbar -->
    <div class="pdf-toolbar">
      <button class="pdf-tool-btn" @click="goToPrevPage" :disabled="currentPage <= 1">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg>
      </button>
      <span class="pdf-page-info">{{ currentPage }} / {{ totalPages }}</span>
      <button class="pdf-tool-btn" @click="goToNextPage" :disabled="currentPage >= totalPages">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
      </button>
      <span class="pdf-toolbar-sep"></span>
      <button class="pdf-tool-btn" @click="zoomOut" :disabled="scale <= 0.5">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="12" x2="19" y2="12"/></svg>
      </button>
      <span class="pdf-zoom-info">{{ Math.round(scale * 100) }}%</span>
      <button class="pdf-tool-btn" @click="zoomIn" :disabled="scale >= 3">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, nextTick, computed } from "vue";
import { getDocument, GlobalWorkerOptions, TextLayer } from "pdfjs-dist";
import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";

GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).href;

const props = withDefaults(
  defineProps<{
    url: string;
    page?: number;
    highlightText?: string;
  }>(),
  { page: 1, highlightText: "" }
);

const rootEl = ref<HTMLElement | null>(null);
const pagesContainer = ref<HTMLElement | null>(null);
const loading = ref(true);
const error = ref("");
const totalPages = ref(0);
const currentPage = ref(1);
const scale = ref(1);

const canvasRefs = new Map<number, HTMLCanvasElement>();
const textRefs = new Map<number, HTMLElement>();
const pageRefs = new Map<number, HTMLElement>();
const pageProxies = new Map<number, PDFPageProxy>();

let pdfDoc: PDFDocumentProxy | null = null;
let highlightDone = false;

// Render a window of pages around the current one for smooth scrolling
const isMobileDevice = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
const BUFFER = isMobileDevice ? 0 : 1;
const renderedPages = computed(() => {
  const pages: number[] = [];
  const start = Math.max(1, currentPage.value - BUFFER);
  const end = Math.min(totalPages.value, currentPage.value + BUFFER);
  for (let i = start; i <= end; i++) pages.push(i);
  return pages;
});

function setCanvasRef(pg: number, el: HTMLCanvasElement | null) {
  if (el) canvasRefs.set(pg, el); else canvasRefs.delete(pg);
}
function setTextRef(pg: number, el: HTMLElement | null) {
  if (el) textRefs.set(pg, el); else textRefs.delete(pg);
}
function setPageRef(pg: number, el: HTMLElement | null) {
  if (el) pageRefs.set(pg, el); else pageRefs.delete(pg);
}

async function loadPdf() {
  try {
    const task = getDocument(props.url);
    pdfDoc = await task.promise;
    totalPages.value = pdfDoc.numPages;
    currentPage.value = Math.min(Math.max(props.page, 1), pdfDoc.numPages);
    loading.value = false;

    await nextTick();
    try {
      await renderVisiblePages();
    } catch (renderErr) {
      console.warn("PDF render failed (pages still navigable):", renderErr);
    }
  } catch (err) {
    console.error("PDF load failed:", err);
    error.value = "Could not load PDF";
    loading.value = false;
  }
}

async function getPageProxy(pageNum: number): Promise<PDFPageProxy> {
  if (pageProxies.has(pageNum)) return pageProxies.get(pageNum)!;
  const page = await pdfDoc!.getPage(pageNum);
  pageProxies.set(pageNum, page);
  return page;
}

async function renderPage(pageNum: number) {
  const canvas = canvasRefs.get(pageNum);
  const textDiv = textRefs.get(pageNum);
  if (!canvas || !textDiv || !pdfDoc) return;

  // Skip if already rendered at this scale
  const scaleKey = `rendered-${scale.value}`;
  if (canvas.dataset.scaleKey === scaleKey) return;
  canvas.dataset.scaleKey = scaleKey;

  const page = await getPageProxy(pageNum);

  const containerWidth = rootEl.value?.clientWidth || 600;
  const unscaledVp = page.getViewport({ scale: 1 });
  const baseScale = (containerWidth - 24) / unscaledVp.width; // 12px padding each side
  const effectiveScale = baseScale * scale.value;
  const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
  const dpr = Math.min(window.devicePixelRatio || 1, isMobile ? 1.5 : 2);
  const viewport = page.getViewport({ scale: effectiveScale * dpr });
  const displayViewport = page.getViewport({ scale: effectiveScale });

  canvas.width = viewport.width;
  canvas.height = viewport.height;
  canvas.style.width = displayViewport.width + "px";
  canvas.style.height = displayViewport.height + "px";

  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  await page.render({ canvas, canvasContext: ctx, viewport }).promise;

  // Text layer
  textDiv.innerHTML = "";
  textDiv.style.width = displayViewport.width + "px";
  textDiv.style.height = displayViewport.height + "px";

  // Set the CSS variable for text scaling
  const scaleFactor = displayViewport.scale;
  textDiv.style.setProperty("--total-scale-factor", String(scaleFactor));

  const textContent = await page.getTextContent();
  const textLayer = new TextLayer({
    textContentSource: textContent,
    container: textDiv,
    viewport: displayViewport,
  });
  await textLayer.render();

  // Highlight matching text on the target page
  if (pageNum === currentPage.value && props.highlightText && !highlightDone) {
    await nextTick();
    highlightTextInLayer(textDiv);
  }
}

async function renderVisiblePages() {
  for (const pg of renderedPages.value) {
    try {
      await renderPage(pg);
    } catch (err) {
      console.warn(`PDF page ${pg} render failed:`, err);
    }
  }
}

/** Normalize text for fuzzy comparison */
function normalizeText(s: string): string {
  return s
    .replace(/[\r\n]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/[""]/g, '"')
    .replace(/['']/g, "'")
    .replace(/[–—]/g, "-")
    .trim()
    .toLowerCase();
}

/**
 * Find contiguous text layer spans matching the source highlight text
 * and apply highlight styling + scroll into view.
 */
function highlightTextInLayer(textDiv: HTMLElement) {
  const sourceText = normalizeText(props.highlightText);
  if (!sourceText || sourceText.length < 10) return;

  const spans = Array.from(textDiv.querySelectorAll("span")) as HTMLElement[];
  if (!spans.length) return;

  // Build a concatenated string of all span texts with position map
  const items: { span: HTMLElement; start: number; text: string }[] = [];
  let concat = "";
  for (const span of spans) {
    const text = span.textContent || "";
    items.push({ span, start: concat.length, text });
    concat += normalizeText(text) + " ";
  }
  const fullText = concat.trimEnd();

  // Find the best matching substring using progressive word matching
  const sourceWords = sourceText.split(/\s+/);
  // Take first N words to search for start position
  const searchPrefix = sourceWords.slice(0, Math.min(8, sourceWords.length)).join(" ");
  const startIdx = fullText.indexOf(searchPrefix);
  if (startIdx === -1) {
    // Try shorter prefix
    const shortPrefix = sourceWords.slice(0, Math.min(4, sourceWords.length)).join(" ");
    const shortIdx = fullText.indexOf(shortPrefix);
    if (shortIdx === -1) return;
    applyHighlight(items, shortIdx, shortIdx + sourceText.length, fullText);
    return;
  }

  applyHighlight(items, startIdx, startIdx + sourceText.length, fullText);
}

function applyHighlight(
  items: { span: HTMLElement; start: number; text: string }[],
  matchStart: number,
  matchEnd: number,
  fullText: string,
) {
  // Clamp matchEnd to actual text length
  const effectiveEnd = Math.min(matchEnd, fullText.length);
  let firstHighlighted: HTMLElement | null = null;

  for (const item of items) {
    const spanEnd = item.start + normalizeText(item.text).length;
    // Check if this span overlaps the matched range
    if (spanEnd > matchStart && item.start < effectiveEnd) {
      item.span.classList.add("pdf-highlight");
      if (!firstHighlighted) firstHighlighted = item.span;
    }
  }

  highlightDone = true;

  // Scroll to highlighted text
  if (firstHighlighted) {
    requestAnimationFrame(() => {
      const container = pagesContainer.value;
      if (!container || !firstHighlighted) return;
      const containerRect = container.getBoundingClientRect();
      const highlightRect = firstHighlighted.getBoundingClientRect();
      // Scroll so highlight is ~30% from the top of the viewer
      const targetOffset = highlightRect.top - containerRect.top - container.clientHeight * 0.3;
      container.scrollTop = Math.max(0, container.scrollTop + targetOffset);
    });
  }
}

function goToPrevPage() {
  if (currentPage.value > 1) {
    currentPage.value--;
    highlightDone = false;
    onPageChange();
  }
}

function goToNextPage() {
  if (currentPage.value < totalPages.value) {
    currentPage.value++;
    highlightDone = false;
    onPageChange();
  }
}

async function onPageChange() {
  await nextTick();
  // Reset canvas scale keys for re-render
  for (const canvas of canvasRefs.values()) {
    canvas.dataset.scaleKey = "";
  }
  await renderVisiblePages();
  // Scroll to top of the current page
  const pageEl = pageRefs.get(currentPage.value);
  if (pageEl && pagesContainer.value) {
    pageEl.scrollIntoView({ block: "start", behavior: "instant" });
  }
}

function zoomIn() {
  if (scale.value >= 3) return;
  scale.value = Math.round((scale.value + 0.25) * 100) / 100;
  reRender();
}

function zoomOut() {
  if (scale.value <= 0.5) return;
  scale.value = Math.round((scale.value - 0.25) * 100) / 100;
  reRender();
}

async function reRender() {
  // Clear scale keys to force re-render
  for (const canvas of canvasRefs.values()) {
    canvas.dataset.scaleKey = "";
  }
  await nextTick();
  await renderVisiblePages();
}

function onWheel(e: WheelEvent) {
  if (e.ctrlKey || e.metaKey) {
    e.preventDefault();
    if (e.deltaY < 0) zoomIn();
    else zoomOut();
  }
}

// Watch for scroll to detect page changes
function onScroll() {
  if (!pagesContainer.value) return;
  const container = pagesContainer.value;
  const containerTop = container.scrollTop + container.clientHeight * 0.4;
  for (const [pg, el] of pageRefs.entries()) {
    if (el.offsetTop <= containerTop && el.offsetTop + el.offsetHeight > containerTop) {
      if (pg !== currentPage.value) {
        currentPage.value = pg;
      }
      break;
    }
  }
}

onMounted(() => {
  loadPdf();
  pagesContainer.value?.addEventListener("scroll", onScroll, { passive: true });
});

onBeforeUnmount(() => {
  pagesContainer.value?.removeEventListener("scroll", onScroll);
  pdfDoc?.destroy();
  pageProxies.clear();
});

// Re-render when rendered pages change (due to page navigation)
watch(renderedPages, async () => {
  await nextTick();
  await renderVisiblePages();
});
</script>

<style>
/* Import the pdfjs textLayer CSS essentials inline
   since the full pdf_viewer.css is very large */
.pdf-page-viewer .textLayer {
  position: absolute;
  top: 0;
  left: 0;
  overflow: hidden;
  opacity: 1;
  line-height: 1;
  -webkit-text-size-adjust: none;
     -moz-text-size-adjust: none;
          text-size-adjust: none;
  forced-color-adjust: none;
  z-index: 2;
}

.pdf-page-viewer .textLayer :is(span, br) {
  color: transparent;
  position: absolute;
  white-space: pre;
  cursor: text;
  transform-origin: 0% 0%;
}

.pdf-page-viewer .textLayer span.markedContent {
  top: 0;
  height: 0;
}

.pdf-page-viewer .textLayer .highlight {
  margin: -1px;
  padding: 1px;
  background-color: rgb(180 0 170 / 0.25);
  border-radius: 4px;
}

.pdf-page-viewer .textLayer ::selection {
  background: rgba(0, 100, 255, 0.3);
}

/* Custom highlight for source text matching */
.pdf-page-viewer .textLayer .pdf-highlight {
  background-color: rgba(59, 130, 246, 0.35);
  border-radius: 2px;
  margin: -1px;
  padding: 1px;
}
</style>

<style scoped>
.pdf-page-viewer {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #333;
  overflow: hidden;
}

.pdf-pages-container {
  flex: 1;
  min-height: 0;
  overflow: auto;
  -webkit-overflow-scrolling: touch;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
  padding: 0;
}


.pdf-page-wrapper {
  position: relative;
  background: #fff;
  box-shadow: none;
  flex-shrink: 0;
  width: 100%;
}

.pdf-page-canvas {
  display: block;
  width: 100% !important;
}

.pdf-page-loading,
.pdf-page-error {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  color: #94a3b8;
  font-size: 14px;
}

/* Toolbar */
.pdf-toolbar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 6px 12px;
  background: #2d2d2d;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}

.pdf-tool-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #cbd5e1;
  cursor: pointer;
  transition: background 0.15s;
}

@media (hover: hover) {
  .pdf-tool-btn:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.1);
  }
}

.pdf-tool-btn:disabled {
  opacity: 0.3;
  cursor: default;
}

.pdf-page-info,
.pdf-zoom-info {
  font-size: 12px;
  color: #94a3b8;
  min-width: 50px;
  text-align: center;
  user-select: none;
}

.pdf-toolbar-sep {
  width: 1px;
  height: 16px;
  background: rgba(255, 255, 255, 0.12);
  margin: 0 4px;
}
</style>
