<template>
  <div class="message" :class="msg.role">
    <strong>{{ msg.role === 'user' ? 'You' : 'Assistant' }}</strong>
    <div v-if="msg.role === 'assistant' && !msg.content && asking" class="typing-dots">
      <span></span><span></span><span></span>
    </div>
    <div v-else-if="msg.role === 'assistant'" ref="contentEl" class="markdown-content" @click="onContentClick" v-html="renderedContent"></div>
    <p v-else style="white-space: pre-wrap">{{ msg.content }}</p>

    <!-- Inline image thumbnails from citations -->
    <div v-if="imageCitations.length" class="citation-images">
      <div
        v-for="(img, idx) in imageCitations"
        :key="idx"
        class="citation-image-thumb"
        @click="openImage(img)"
      >
        <img :src="img.url" :alt="img.section || 'Image'" loading="lazy" />
        <span class="citation-image-label">{{ img.section || 'Image' }}</span>
      </div>
    </div>



    <ImageModal
      :visible="modalOpen"
      :src="modalSrc"
      :alt="modalAlt"
      @close="modalOpen = false"
    />

    <SourcePreviewModal
      v-if="previewCitation"
      :visible="previewOpen"
      :citation="previewCitation"
      :conversationId="conversationId"
      @close="previewOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick, onBeforeUnmount } from "vue";
import { marked } from "marked";
import DOMPurify from "dompurify";
import { createTooltip, destroyTooltip } from "floating-vue";
import type { ChatMessage } from "../api";
import { getStorageUrl } from "../api";
import ImageModal from "./ImageModal.vue";
import SourcePreviewModal from "./SourcePreviewModal.vue";

marked.setOptions({
  breaks: true,
  gfm: true,
});

function normalizeCitations(text: string): string {
  // Convert bare [N] references to [source:N] format
  // Handles [1][2][3], [1,2,3,4], [1, 2, 3], etc.
  // First: comma-separated like [1,2,3,4] or [1, 2, 3, 4]
  text = text.replace(
    /\[(\d+(?:\s*,\s*\d+)+)\]/g,
    (_, nums) => nums.split(/\s*,\s*/).map((n: string) => `[source:${n.trim()}]`).join('')
  );
  // Then: bare single [N] (not already [source:N])
  text = text.replace(
    /(?<!source:)(?<!\w)\[(\d+)\](?!\()/g,
    (_, n) => `[source:${n}]`
  );
  return text;
}

function renderMarkdown(content: string): string {
  const normalized = normalizeCitations(content);
  const rawHtml = marked.parse(normalized, { async: false }) as string;
  const sanitized = DOMPurify.sanitize(rawHtml);
  // Replace [source:N] or [source:N,N,...] markers with clickable inline source buttons
  return sanitized.replace(
    /\[source:\s*(\d+(?:,\s*\d+)*)\]/g,
    (_, nums) =>
      nums.split(/,\s*/).map((n: string) =>
        `<button class="inline-source-btn" data-source-idx="${parseInt(n, 10)}">` +
        `<span class="inline-source-icon">↑</span>${n.trim()}</button>`
      ).join('')
  );
}

const props = defineProps<{
  msg: ChatMessage;
  asking: boolean;
  conversationId: string;
}>();

const renderedContent = computed(() => renderMarkdown(props.msg.content));

// Source preview modal state
const previewOpen = ref(false);
const previewCitation = ref<{ fileName: string; chunkId: string; text: string; section?: string; page?: number | null; imageName?: string }>();

// Tooltip management for inline source buttons
const contentEl = ref<HTMLElement>();
const tooltipElements: HTMLElement[] = [];
const MAX_TOOLTIP_LENGTH = 600;

function truncateText(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + '…';
}

function setupTooltips() {
  cleanupTooltips();
  if (!contentEl.value) return;
  const buttons = contentEl.value.querySelectorAll<HTMLElement>('.inline-source-btn');
  buttons.forEach((btn) => {
    const idx = parseInt(btn.dataset.sourceIdx || '0', 10) - 1;
    const citation = props.msg.citations?.[idx];
    if (!citation?.text) return;
    createTooltip(btn, {
      content: truncateText(citation.text, MAX_TOOLTIP_LENGTH),
      delay: { show: 1000, hide: 0 },
      themes: ['tooltip'],
    }, false);
    tooltipElements.push(btn);
  });
}

function cleanupTooltips() {
  tooltipElements.forEach((el) => {
    try { destroyTooltip(el); } catch {}
  });
  tooltipElements.length = 0;
}

watch(renderedContent, () => {
  nextTick(setupTooltips);
}, { immediate: true });

onBeforeUnmount(cleanupTooltips);

function onContentClick(e: MouseEvent) {
  const btn = (e.target as HTMLElement).closest(".inline-source-btn") as HTMLElement | null;
  if (!btn) return;
  const idx = parseInt(btn.dataset.sourceIdx || "0", 10) - 1; // 1-based to 0-based
  if (props.msg.citations && props.msg.citations[idx]) {
    previewCitation.value = props.msg.citations[idx] as any;
    previewOpen.value = true;
  }
}

// Image modal state
const modalOpen = ref(false);
const modalSrc = ref("");
const modalAlt = ref("");

type ImageCitationInfo = { url: string; section?: string; imageName: string };

function resolveImageCitation(citation: any): ImageCitationInfo {
  return {
    url: getStorageUrl(props.conversationId, citation.imageName),
    section: citation.section,
    imageName: citation.imageName,
  };
}

const imageCitations = computed<ImageCitationInfo[]>(() => {
  if (!props.msg.citations) return [];
  return props.msg.citations
    .filter((c) => c.imageName)
    .map((c) => resolveImageCitation(c));
});

function openImage(img: ImageCitationInfo) {
  modalSrc.value = img.url;
  modalAlt.value = img.section || "Image";
  modalOpen.value = true;
}
</script>

<style scoped>
/* Inline source buttons */
:deep(.inline-source-btn) {
  display: inline-flex;
  align-items: center;
  gap: 1px;
  background: #7c3aed33;
  color: #c4b5fd;
  border: 1px solid #7c3aed55;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  padding: 0 5px;
  margin: 0 1px;
  cursor: pointer;
  vertical-align: super;
  line-height: 1.4;
  transition: background 0.15s, border-color 0.15s;
  font-family: inherit;
}

:deep(.inline-source-btn:hover) {
  background: #7c3aed55;
  border-color: #a78bfa;
}

:deep(.inline-source-icon) {
  font-size: 9px;
}

/* Image thumbnails */
.citation-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0 4px;
}

.citation-image-thumb {
  cursor: pointer;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #334155;
  transition: border-color 0.15s, transform 0.15s;
  max-width: 140px;
}

.citation-image-thumb:hover {
  border-color: #c4b5fd;
  transform: scale(1.03);
}

.citation-image-thumb img {
  display: block;
  width: 140px;
  height: 100px;
  object-fit: cover;
}

.citation-image-label {
  display: block;
  padding: 4px 6px;
  font-size: 11px;
  color: #94a3b8;
  background: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.citation-active-image {
  margin: 8px 0;
  cursor: pointer;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #334155;
  display: inline-block;
  transition: border-color 0.15s;
}

.citation-active-image:hover {
  border-color: #c4b5fd;
}

.citation-active-image img {
  display: block;
  max-width: 100%;
  max-height: 300px;
  object-fit: contain;
}
</style>
