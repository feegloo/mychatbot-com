<template>
  <div ref="containerRef" class="mobile-pdf-viewer">
    <div v-if="loading" class="mobile-pdf-loading">Loading…</div>
    <div v-if="error" class="mobile-pdf-error">{{ error }}</div>
    <canvas v-show="!loading && !error" ref="canvasRef" class="mobile-pdf-canvas" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from "vue";
import { getDocument, GlobalWorkerOptions } from "pdfjs-dist";
import type { PDFDocumentProxy } from "pdfjs-dist";

GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).href;

const props = withDefaults(
  defineProps<{
    url: string;
    page?: number;
  }>(),
  { page: 1 }
);

const containerRef = ref<HTMLElement | null>(null);
const canvasRef = ref<HTMLCanvasElement | null>(null);
const loading = ref(true);
const error = ref("");

let pdfDoc: PDFDocumentProxy | null = null;

async function loadPdf() {
  try {
    const task = getDocument(props.url);
    pdfDoc = await task.promise;

    const targetPage = Math.min(Math.max(props.page, 1), pdfDoc.numPages);
    const page = await pdfDoc.getPage(targetPage);

    const canvas = canvasRef.value;
    if (!canvas) return;

    const containerWidth = containerRef.value?.clientWidth || 300;
    const unscaledVp = page.getViewport({ scale: 1 });
    const baseScale = containerWidth / unscaledVp.width;
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    const viewport = page.getViewport({ scale: baseScale * dpr });

    canvas.width = viewport.width;
    canvas.height = viewport.height;
    canvas.style.width = containerWidth + "px";
    canvas.style.height =
      (containerWidth * unscaledVp.height) / unscaledVp.width + "px";

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    await page.render({ canvas, canvasContext: ctx, viewport }).promise;
    loading.value = false;
  } catch (err) {
    console.error("Failed to load PDF:", err);
    error.value = "Could not load PDF";
    loading.value = false;
  }
}

onMounted(loadPdf);

onBeforeUnmount(() => {
  pdfDoc?.destroy();
});
</script>

<style scoped>
.mobile-pdf-viewer {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  background: #525659;
}

.mobile-pdf-loading,
.mobile-pdf-error {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: #94a3b8;
  font-size: 14px;
}

.mobile-pdf-canvas {
  display: block;
}
</style>
