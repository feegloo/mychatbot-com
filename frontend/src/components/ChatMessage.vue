<template>
  <div class="message" :class="[msg.role, { 'welcome-message': isWelcome }]">
    <strong>{{ senderLabel }}</strong>
    <AppButton
      v-if="hasRichContent"
      class="share-msg-btn pdf-msg-btn"
      title="Download PDF"
      @click="downloadMessagePdf"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
      PDF
    </AppButton>
    <AppButton
      v-if="msg.role === 'assistant' && msg.id && msg.content"
      class="share-msg-btn"
      :title="shareCopied ? 'Copied!' : 'Share this answer'"
      @click="shareMessage"
    >
      <svg v-if="!shareCopied" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
      <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
      {{ shareCopied ? 'Copied!' : 'Share' }}
    </AppButton>
    <div v-if="msg.role === 'assistant' && !msg.content && asking" class="typing-dots">
      <span></span><span></span><span></span>
    </div>

    <!-- Welcome message with file preview: 2-column on desktop, stacked on mobile -->
    <div v-else-if="welcomeHasFiles && msg.role === 'assistant'" class="welcome-two-col">
      <div class="welcome-left-col">
        <div ref="messageContentEl" class="message-content-wrap">
          <div v-for="(part, pi) in contentParts" :key="pi">
            <div v-if="part.type === 'text'" ref="contentEls" class="markdown-content" @click="onContentClick" v-html="part.html"></div>
            <QuizBlock v-else-if="part.type === 'quiz'" :quiz="part.quiz" :messageId="msg.id" :quizIndex="part.quizIndex" :conversationName="conversationName" :fileName="fileName" />
            <MermaidBlock v-else-if="part.type === 'mermaid'" :code="part.code" />
          </div>
        </div>

        <!-- Mobile-only: small file thumbnails (old layout) -->
        <div class="welcome-file-previews-mobile">
          <div
            v-for="file in files"
            :key="file.id"
            class="file-preview-card"
            @click="openFilePreview(file)"
          >
            <div v-if="isImageFile(file)" class="file-preview-thumb">
              <img :src="getFileUrl(file)" :alt="file.originalName" loading="lazy" />
            </div>
            <div v-else-if="isPdfFile(file)" class="file-preview-thumb pdf-thumb">
              <object
                :data="getFileUrl(file) + '#page=1&view=FitH'"
                type="application/pdf"
                class="pdf-mini-object"
              >
                <div class="pdf-fallback-icon">
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
                </div>
              </object>
              <div class="pdf-click-overlay"></div>
            </div>
            <div v-else class="file-preview-thumb text-thumb">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
            </div>
            <span class="file-preview-name">{{ file.originalName }}</span>
          </div>
        </div>

        <div v-if="suggestedQuestions?.length" class="welcome-suggested-questions">
          <AppButton v-for="q in suggestedQuestions" :key="q" class="question-pill" @click="$emit('select-question', q)">
            {{ q }}
          </AppButton>
        </div>

        <div v-if="isFirstMessage && canUpload" class="welcome-upload-row">
          <input ref="uploadInput" type="file" multiple @change="onUploadFilesChange" style="display:none" />
          <AppButton class="upload-inline-btn" @click="uploadInput?.click()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: -2px; margin-right: 4px"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            Upload more files
          </AppButton>
          <template v-if="selectedUploadFiles.length">
            <span v-for="file in selectedUploadFiles" :key="file.name" class="upload-file-name">{{ file.name }}</span>
            <span v-if="uploadingFiles" class="upload-file-status">Uploading…</span>
          </template>
          <span v-if="uploadError" class="upload-error">{{ uploadError }}</span>
        </div>
      </div>

      <!-- Desktop-only: large preview in right column -->
      <div class="welcome-right-col" @click="openFilePreview(files![0])">
        <div v-if="isImageFile(files![0])" class="welcome-preview-large">
          <img :src="getFileUrl(files![0])" :alt="files![0].originalName" loading="lazy" />
        </div>
        <div v-else-if="isPdfFile(files![0])" class="welcome-preview-large pdf-preview-large">
          <object
            :data="getFileUrl(files![0]) + '#page=1&view=FitH'"
            type="application/pdf"
            class="pdf-large-object"
          >
            <div class="pdf-fallback-icon-large">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
              <span class="pdf-fallback-label">{{ files![0].originalName }}</span>
            </div>
          </object>
          <div class="pdf-click-overlay"></div>
        </div>
        <div v-else class="welcome-preview-large text-preview-large">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
          <span class="text-fallback-label">{{ files![0].originalName }}</span>
        </div>
        <span class="welcome-preview-name">{{ files![0].originalName }}</span>
      </div>
    </div>

    <!-- Regular assistant content -->
    <template v-else-if="msg.role === 'assistant'">
      <div ref="messageContentEl" class="message-content-wrap">
      <div v-for="(part, pi) in contentParts" :key="pi">
        <div v-if="part.type === 'text'" ref="contentEls" class="markdown-content" @click="onContentClick" v-html="part.html"></div>
        <QuizBlock v-else-if="part.type === 'quiz'" :quiz="part.quiz" :messageId="msg.id" :quizIndex="part.quizIndex" :conversationName="conversationName" :fileName="fileName" />
        <MermaidBlock v-else-if="part.type === 'mermaid'" :code="part.code" />
      </div>
      </div>
    </template>
    <span v-else class="user-text">{{ msg.content }}</span>

    <!-- Inline suggested questions for welcome message (non-2-col fallback) -->
    <div v-if="isWelcome && !welcomeHasFiles && suggestedQuestions?.length" class="welcome-suggested-questions">
      <AppButton
        v-for="q in suggestedQuestions"
        :key="q"
        class="question-pill"
        @click="$emit('select-question', q)"
      >
        {{ q }}
      </AppButton>
    </div>

    <!-- Upload files button (first message only, non-2-col fallback) -->
    <div v-if="isFirstMessage && canUpload && !welcomeHasFiles" class="welcome-upload-row">
      <input ref="uploadInput" type="file" multiple @change="onUploadFilesChange" style="display:none" />
      <AppButton class="upload-inline-btn" @click="uploadInput?.click()">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: -2px; margin-right: 4px"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
        Upload more files
      </AppButton>
      <template v-if="selectedUploadFiles.length">
        <span v-for="file in selectedUploadFiles" :key="file.name" class="upload-file-name">{{ file.name }}</span>
        <span v-if="uploadingFiles" class="upload-file-status">Uploading…</span>
      </template>
      <span v-if="uploadError" class="upload-error">{{ uploadError }}</span>
    </div>

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

    <!-- Thread reply indicator (Slack-style) -->
    <div v-if="msg.threadReplyCount" class="thread-indicator" @click="$emit('view-threads', msg.id!)">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
      <span class="thread-count">{{ msg.threadReplyCount }} {{ msg.threadReplyCount === 1 ? 'reply' : 'replies' }}</span>
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
import type { ChatMessage, ConversationStatus } from "../api";
import { getStorageUrl } from "../api";
import { getUserId } from "../utils/fingerprint";
import ImageModal from "./ImageModal.vue";
import SourcePreviewModal from "./SourcePreviewModal.vue";
import AppButton from "./AppButton.vue";
import QuizBlock from "./QuizBlock.vue";
import MermaidBlock from "./MermaidBlock.vue";
import type { QuizData } from "./QuizBlock.vue";
import { getData, setData } from "../utils/localData";
import { printContentAsPdf } from "../utils/printPdf";

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
  let normalized = normalizeCitations(content);
  // Ensure bold-only lines (like filenames) between list items get paragraph separation
  normalized = normalized.replace(
    /^([ \t]*[\*\-\+] .+)\n(\*\*[^*\n]+\*\*)\n([ \t]*[\*\-\+] )/gm,
    '$1\n\n$2\n\n$3'
  );
  const rawHtml = marked.parse(normalized, { async: false }) as string;
  // Replace disabled checkboxes BEFORE DOMPurify (which may strip <input> tags)
  // Use flexible regex to handle any attribute order from marked
  const withChecklists = rawHtml
    .replace(/<input\s+(?=[^>]*type="checkbox")(?=[^>]*disabled="")[^>]*checked=""[^>]*\/?>/gi,
      '<span class="checklist-box checked" role="checkbox" tabindex="0"></span>')
    .replace(/<input\s+(?=[^>]*type="checkbox")(?=[^>]*disabled="")[^>]*\/?>/gi,
      '<span class="checklist-box" role="checkbox" tabindex="0"></span>');
  const sanitized = DOMPurify.sanitize(withChecklists);
  // Replace [source:N] or [source:N,N,...] markers with clickable inline source buttons
  const withSources = sanitized.replace(
    /\[source:\s*(\d+(?:,\s*\d+)*)\]/g,
    (_, nums) =>
      nums.split(/,\s*/).map((n: string) =>
        `<button class="inline-source-btn" data-source-idx="${parseInt(n, 10)}">` +
        `<span class="inline-source-icon">↑</span>${n.trim()}</button>`
      ).join('')
  );
  // Replace [action:Label] markers with clickable action buttons wrapped in a block container
  const withActions = withSources.replace(
    /\[action:\s*([^\]]+)\]/g,
    (_, label) =>
      `<button class="action-btn" data-action="${label.trim()}">${label.trim()}</button>`
  );
  // Wrap consecutive action buttons in a block-level container so they start on a new line
  const withActionsWrapped = withActions.replace(
    /(<button class="action-btn"[^>]*>.*?<\/button>(?:\s*<button class="action-btn"[^>]*>.*?<\/button>)*)/g,
    '<div class="action-btns-row">$1</div>'
  );
  // Add target="_blank" to all <a> tags that don't already have it
  const withTargetBlank = withActionsWrapped.replace(
    /<a (?![^>]*target=)/gi,
    '<a target="_blank" rel="noopener noreferrer" '
  );
  // Linkify bare domain URLs in text nodes (not inside existing <a> tags)
  const tlds = 'com|org|net|io|dev|pl|eu|co|info|me|app|xyz|tech|ai';
  const bareDomain = new RegExp(
    `\\b((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\\.)+(?:${tlds}))(\\/[^\\s<"'\u201C\u201D\u2018\u2019\u00AB\u00BB.,;:!?)\\]]*)?`,
    'gi'
  );
  let insideA = 0;
  return withTargetBlank.replace(
    /(<a\b[^>]*>)|(<\/a>)|(<[^>]*>)|([^<]+)/gi,
    (m, openA: string, closeA: string, _otherTag: string, text: string) => {
      if (openA) { insideA++; return m; }
      if (closeA) { insideA = Math.max(0, insideA - 1); return m; }
      if (text && insideA === 0) {
        return text.replace(bareDomain, (url: string, domain: string, path: string) => {
          const href = `https://${domain}${path || ''}`;
          return `<a href="${href}" target="_blank" rel="noopener noreferrer" style="color: #60a5fa;">${url}</a>`;
        });
      }
      return m;
    }
  );
}

const props = defineProps<{
  msg: ChatMessage;
  asking: boolean;
  conversationId: string;
  isWelcome?: boolean;
  isFirstMessage?: boolean;
  canUpload?: boolean;
  files?: ConversationStatus["files"];
  suggestedQuestions?: string[];
  conversationName?: string;
  fileName?: string;
  isThread?: boolean;
}>();

const emit = defineEmits<{
  'select-question': [question: string];
  'upload-files': [files: File[]];
  'view-threads': [messageId: string];
}>();

const senderLabel = computed(() => {
  if (props.msg.role === "assistant") return "Assistant";
  // In thread conversations, show "userN" for other users
  if (props.isThread && props.msg.userId) {
    const myId = getUserId();
    if (myId !== null && props.msg.userId === myId) return "You";
    return `user${props.msg.userId}`;
  }
  return "You";
});

// Upload files state (for first message inline upload)
const uploadInput = ref<HTMLInputElement | null>(null);
const selectedUploadFiles = ref<File[]>([]);
const uploadingFiles = ref(false);
const uploadError = ref("");

const welcomeHasFiles = computed(() => props.isWelcome && (props.files?.length ?? 0) > 0);


function onUploadFilesChange(event: Event) {
  const target = event.target as HTMLInputElement;
  selectedUploadFiles.value = Array.from(target.files || []);
  uploadError.value = "";
  if (selectedUploadFiles.value.length) {
    doUploadFiles();
  }
}

function doUploadFiles() {
  if (!selectedUploadFiles.value.length) return;
  emit('upload-files', selectedUploadFiles.value);
}

function resetUploadState(error?: string) {
  selectedUploadFiles.value = [];
  uploadingFiles.value = false;
  uploadError.value = error || "";
  if (uploadInput.value) uploadInput.value.value = "";
}

// Share message
const shareCopied = ref(false);
function shareMessage() {
  if (!props.msg.id) return;
  const url = `${window.location.origin}/m/${props.msg.id}`;
  navigator.clipboard.writeText(url);
  shareCopied.value = true;
  setTimeout(() => { shareCopied.value = false; }, 2000);
}

function setUploading(val: boolean) {
  uploadingFiles.value = val;
}

defineExpose({ resetUploadState, setUploading });

const renderedContent = computed(() => renderMarkdown(props.msg.content));

const messageContentEl = ref<HTMLElement | null>(null);

/** Detect if this message has rich/custom rendered content worth downloading as PDF */
const hasRichContent = computed(() => {
  if (props.msg.role !== "assistant" || !props.msg.content) return false;
  const parts = contentParts.value;
  // Has quiz or mermaid blocks
  if (parts.some((p) => p.type === "quiz" || p.type === "mermaid")) return true;
  // Has tables or checklists in rendered HTML
  for (const p of parts) {
    if (p.type === "text") {
      if (/<table[\s>]/i.test(p.html)) return true;
      if (/checklist-box/i.test(p.html)) return true;
    }
  }
  return false;
});

function downloadMessagePdf() {
  if (!messageContentEl.value) return;
  const html = messageContentEl.value.innerHTML;
  const title = props.conversationName || "chatrag";
  printContentAsPdf(html, title);
}

type ContentPart =
  | { type: 'text'; html: string }
  | { type: 'quiz'; quiz: QuizData; quizIndex: number }
  | { type: 'mermaid'; code: string };

// Mermaid diagram detection regex: ```mermaid ... ```
const mermaidBlockRe = /```mermaid\s*\n([\s\S]*?)```/g;

/** Split a text chunk into interleaved text and mermaid parts */
function splitMermaid(text: string): ContentPart[] {
  const result: ContentPart[] = [];
  let lastIdx = 0;
  for (const m of text.matchAll(mermaidBlockRe)) {
    const before = text.slice(lastIdx, m.index);
    if (before.trim()) result.push({ type: 'text', html: renderMarkdown(before) });
    result.push({ type: 'mermaid', code: m[1].trim() });
    lastIdx = m.index! + m[0].length;
  }
  const after = text.slice(lastIdx);
  if (after.trim()) result.push({ type: 'text', html: renderMarkdown(after) });
  return result;
}

const contentParts = computed<ContentPart[]>(() => {
  const content = props.msg.content;
  const parts: ContentPart[] = [];
  const marker = '[quiz:';
  let lastIndex = 0;
  let searchFrom = 0;
  let quizCounter = 0;

  while (searchFrom < content.length) {
    const start = content.indexOf(marker, searchFrom);
    if (start === -1) break;

    const jsonStart = start + marker.length;
    // Find matching closing brace by counting braces
    let depth = 0;
    let jsonEnd = -1;
    for (let i = jsonStart; i < content.length; i++) {
      if (content[i] === '{') depth++;
      else if (content[i] === '}') {
        depth--;
        if (depth === 0) {
          // Expect ] after the closing brace (allow optional whitespace)
          let j = i + 1;
          while (j < content.length && /\s/.test(content[j])) j++;
          if (j < content.length && content[j] === ']') {
            jsonEnd = j; // points to ']'
          }
          break;
        }
      }
    }

    if (jsonEnd === -1) {
      searchFrom = start + marker.length;
      continue;
    }

    // Text before quiz (may contain mermaid blocks)
    const textBefore = content.slice(lastIndex, start);
    if (textBefore.trim()) {
      parts.push(...splitMermaid(textBefore));
    }

    // Parse quiz JSON — strip [source:N] citations that break JSON validity
    const jsonStr = content.slice(jsonStart, jsonEnd)
      .replace(/\[source:\s*\d+\]/g, '');
    try {
      const quizData = JSON.parse(jsonStr) as QuizData;
      if (quizData.title && Array.isArray(quizData.questions)) {
        // Normalize correct field to always be an array
        for (const q of quizData.questions) {
          if (!Array.isArray(q.correct)) {
            q.correct = [q.correct as unknown as number];
          }
        }
        parts.push({ type: 'quiz', quiz: quizData, quizIndex: quizCounter++ });
      } else {
        parts.push(...splitMermaid(content.slice(start, jsonEnd + 1)));
      }
    } catch {
      parts.push(...splitMermaid(content.slice(start, jsonEnd + 1)));
    }

    lastIndex = jsonEnd + 1;
    searchFrom = lastIndex;
  }

  // Remaining text after last quiz block (or all text if no quiz)
  const remaining = content.slice(lastIndex);
  if (remaining.trim()) {
    parts.push(...splitMermaid(remaining));
  }

  // If no parts at all, add empty text
  if (!parts.length) {
    parts.push({ type: 'text', html: renderMarkdown(content) });
  }

  return parts;
});

// Source preview modal state
const previewOpen = ref(false);
const previewCitation = ref<{ fileName: string; chunkId: string; text: string; section?: string; page?: number | null; imageName?: string }>();

// Tooltip management for inline source buttons
const contentEls = ref<HTMLElement[]>([]);
const tooltipElements: HTMLElement[] = [];
const MAX_TOOLTIP_LENGTH = 600;

function truncateText(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + '…';
}

function setupTooltips() {
  cleanupTooltips();
  if (!contentEls.value?.length) return;
  for (const el of contentEls.value) {
    const buttons = el.querySelectorAll<HTMLElement>('.inline-source-btn');
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
}

function cleanupTooltips() {
  tooltipElements.forEach((el) => {
    try { destroyTooltip(el); } catch {}
  });
  tooltipElements.length = 0;
}

function injectCodeCopyButtons() {
  if (!contentEls.value?.length) return;
  for (const el of contentEls.value) {
    const pres = el.querySelectorAll<HTMLPreElement>('pre');
    pres.forEach((pre) => {
      if (pre.querySelector('.code-copy-btn')) return;
      // Wrap pre in a relative container
      const wrapper = document.createElement('div');
      wrapper.className = 'code-block-wrapper';
      pre.parentNode!.insertBefore(wrapper, pre);
      wrapper.appendChild(pre);

      const btn = document.createElement('button');
      btn.className = 'code-copy-btn';
      btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copy text`;
      btn.addEventListener('click', () => {
        const code = pre.querySelector('code');
        navigator.clipboard.writeText(code?.textContent || pre.textContent || '');
        btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Copied!`;
        setTimeout(() => {
          btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copy text`;
        }, 2000);
      });
      wrapper.appendChild(btn);
    });
  }
}

watch(contentParts, () => {
  nextTick(() => {
    setupTooltips();
    restoreChecklistState();
    injectCodeCopyButtons();
  });
}, { immediate: true });

onBeforeUnmount(cleanupTooltips);

function saveChecklistState() {
  if (!props.msg.id) return;
  const states: boolean[] = [];
  for (const el of contentEls.value ?? []) {
    el.querySelectorAll('.checklist-box').forEach((box) => {
      states.push(box.classList.contains('checked'));
    });
  }
  if (states.length) {
    setData(`checklist:${props.msg.id}`, states);
  }
}

function restoreChecklistState() {
  if (!props.msg.id) return;
  try {
    const states = getData<boolean[]>(`checklist:${props.msg.id}`);
    if (!states) return;
    let idx = 0;
    for (const el of contentEls.value ?? []) {
      el.querySelectorAll('.checklist-box').forEach((box) => {
        if (idx < states.length && states[idx]) box.classList.add('checked');
        idx++;
      });
    }
  } catch { /* ignore corrupt data */ }
}

function onContentClick(e: MouseEvent) {
  // Handle checklist checkbox clicks (clicking the box or anywhere on the row)
  const checkBox = (e.target as HTMLElement).closest(".checklist-box") as HTMLElement | null;
  if (checkBox) {
    checkBox.classList.toggle("checked");
    saveChecklistState();
    return;
  }
  const li = (e.target as HTMLElement).closest("li") as HTMLElement | null;
  if (li && li.querySelector(".checklist-box")) {
    li.querySelector(".checklist-box")!.classList.toggle("checked");
    saveChecklistState();
    return;
  }

  // Handle action button clicks
  const actionBtn = (e.target as HTMLElement).closest(".action-btn") as HTMLElement | null;
  if (actionBtn) {
    const action = actionBtn.dataset.action;
    if (action) {
      emit('select-question', action);
    }
    return;
  }

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

// Welcome message file preview helpers
type FileInfo = ConversationStatus["files"][number];

function isImageFile(file: FileInfo) {
  return file.mimeType.startsWith("image/");
}

function isPdfFile(file: FileInfo) {
  return file.mimeType === "application/pdf";
}

function getFileUrl(file: FileInfo) {
  return getStorageUrl(props.conversationId, file.originalName);
}

function openFilePreview(file: FileInfo) {
  if (isImageFile(file)) {
    modalSrc.value = getFileUrl(file);
    modalAlt.value = file.originalName;
    modalOpen.value = true;
  } else if (isPdfFile(file)) {
    previewCitation.value = {
      fileName: file.originalName,
      chunkId: "",
      text: "",
      page: 1,
    };
    previewOpen.value = true;
  } else {
    // For text files, open in a new tab
    window.open(getFileUrl(file), "_blank");
  }
}
</script>

<style scoped>
.user-text {
  white-space: pre-wrap;
  margin: 0;
}

/* Share button */
.share-msg-btn {
  position: absolute;
  top: 10px;
  right: 10px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #64748b;
  border-radius: 8px;
  padding: 4px 10px;
  font-size: 11px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
  font-family: inherit;
  opacity: 0;
}

/* On touch devices, always show the share button */
@media (hover: none) {
  .share-msg-btn {
    opacity: 1;
  }
}

@media (hover: hover) {
  .message:hover .share-msg-btn {
    opacity: 1;
  }
}

@media (hover: hover) {
  .share-msg-btn:hover {
    background: rgba(167, 139, 250, 0.12);
    border-color: rgba(167, 139, 250, 0.3);
    color: #c4b5fd;
  }
}
.share-msg-btn:active {
  background: rgba(167, 139, 250, 0.12);
  border-color: rgba(167, 139, 250, 0.3);
  color: #c4b5fd;
  opacity: 1;
}

.pdf-msg-btn {
  right: 80px;
  padding-right: 5px;
}

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

@media (hover: hover) {
  :deep(.inline-source-btn:hover) {
    background: #7c3aed55;
    border-color: #a78bfa;
  }
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

@media (hover: hover) {
  .citation-image-thumb:hover {
    border-color: #c4b5fd;
    transform: scale(1.03);
  }
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

@media (hover: hover) {
  .citation-active-image:hover {
    border-color: #c4b5fd;
  }
}

.citation-active-image img {
  display: block;
  max-width: 100%;
  max-height: 300px;
  object-fit: contain;
}

/* Welcome 2-column layout (desktop only) */
.welcome-two-col {
  display: flex;
  gap: 20px;
  min-height: 160px;
}

.welcome-left-col {
  flex: 1;
  min-width: 0;
}

/* Mobile: small file thumbnails (old layout) */
.welcome-file-previews-mobile {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 12px 0 4px;
}

.file-preview-card {
  cursor: pointer;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.04);
  transition: border-color 0.15s, transform 0.15s, background 0.15s;
  width: 120px;
  flex-shrink: 0;
}

@media (hover: hover) {
  .file-preview-card:hover {
    border-color: #a78bfa;
    background: rgba(167, 139, 250, 0.08);
    transform: scale(1.03);
  }
}

.file-preview-thumb {
  width: 120px;
  height: 90px;
  overflow: hidden;
  background: #0f172a;
  display: flex;
  align-items: center;
  justify-content: center;
}

.file-preview-thumb img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.file-preview-thumb.pdf-thumb {
  position: relative;
}

.pdf-mini-object {
  width: 120px;
  height: 90px;
  pointer-events: none;
  overflow: hidden;
}

.pdf-fallback-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: #64748b;
}

.file-preview-thumb.text-thumb {
  color: #64748b;
}

.file-preview-name {
  display: block;
  padding: 6px 8px;
  font-size: 11px;
  color: #94a3b8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Desktop: large right-column preview */
.welcome-right-col {
  flex-shrink: 0;
  margin-top: 10px;
  align-self: stretch;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0;
  cursor: pointer;
  border-radius: 0;
  border: 1px solid transparent;
  /* background: rgba(255, 255, 255, 0.04); */
  transition: border-color 0.15s, background 0.15s;
  overflow: hidden;
}

@media (hover: hover) {
  .welcome-right-col:hover {
    border: 1px solid #a78bfa;
    /* background: rgba(167, 139, 250, 0.08); */
  }
}

.welcome-preview-large {
  flex: 1;
  min-height: 0;
  max-height: 360px;
  aspect-ratio: 3 / 4;
  overflow: hidden;
  border-radius: 0;
  background: #0f172a;
  display: flex;
  align-items: center;
  justify-content: center;
}

.welcome-preview-large img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 0;
}

.welcome-preview-large.pdf-preview-large {
  position: relative;
}

.pdf-thumb {
  position: relative;
}

.pdf-click-overlay {
  position: absolute;
  inset: 0;
  z-index: 1;
  margin-top: 59px;
  cursor: pointer;
}

.pdf-large-object {
  width: 100%;
  height: 100%;
  pointer-events: none;
  overflow: hidden;
  border-radius: 0;
}

.pdf-fallback-icon-large {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  height: 100%;
  color: #64748b;
}

.pdf-fallback-label,
.text-fallback-label {
  font-size: 11px;
  color: #94a3b8;
  text-align: center;
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.welcome-preview-large.text-preview-large {
  flex-direction: column;
  gap: 8px;
  color: #64748b;
}

.welcome-preview-name {
  display: block;
  padding: 8px 8px 6px;
  font-size: 11px;
  color: #94a3b8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
  text-align: center;
}

/* Responsive: mobile/tablet = small thumbs, wide desktop = large right preview */
@media (max-width: 1024px) {
  .welcome-two-col {
    display: block;
  }
  .welcome-right-col {
    display: none;
  }
  .welcome-file-previews-mobile {
    display: flex;
  }
}

@media (min-width: 1025px) {
  .welcome-file-previews-mobile {
    display: none;
  }
}

/* Welcome suggested questions (inline) */
.welcome-suggested-questions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 14px 0 2px;
}

.welcome-suggested-questions .question-pill {
  margin: 0 6px 8px 0;
}

@media (hover: hover) {
  .welcome-suggested-questions .question-pill:hover {
    background: rgba(167, 139, 250, 0.1);
    border-color: rgba(167, 139, 250, 0.25);
    color: #ddd6fe;
  }
}
.welcome-suggested-questions .question-pill:active {
  background: rgba(167, 139, 250, 0.1);
  border-color: rgba(167, 139, 250, 0.25);
  color: #ddd6fe;
}

/* Upload files row inside first message */
.welcome-upload-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 14px 0 2px;
}

.upload-inline-btn {
  display: inline-flex;
  align-items: center;
  background: rgba(167, 139, 250, 0.12);
  border: 1px solid rgba(167, 139, 250, 0.3);
  color: #c4b5fd;
  border-radius: 10px;
  padding: 4px 14px;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s;
  font-family: inherit;
  height: 26px;
}

@media (hover: hover) {
  .upload-inline-btn:hover {
    background: rgba(167, 139, 250, 0.25);
  }
}
.upload-inline-btn:active {
  background: rgba(167, 139, 250, 0.25);
}

.upload-inline-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.upload-file-name {
  font-size: 12px;
  color: #cbd5e1;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-file-status {
  font-size: 12px;
  color: #a78bfa;
}

.upload-error {
  font-size: 12px;
  color: #fbbf24;
}

:deep(.action-btns-row) {
  display: flex;
  flex-wrap: wrap;
  margin-top: 8px;
}

:deep(.action-btn) {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #94a3b8;
  border-radius: 999px;
  padding: 6px 12px;
  margin: 4px 6px 0 0;
  font-size: 12px;
  cursor: pointer;
  transition: 0.15s;
}

@media (hover: hover) {
  :deep(.action-btn:hover) {
    background: rgba(167, 139, 250, 0.1);
    border-color: rgba(167, 139, 250, 0.25);
    color: #ddd6fe;
  }
}
:deep(.action-btn:active) {
  background: rgba(167, 139, 250, 0.1);
  border-color: rgba(167, 139, 250, 0.25);
  color: #ddd6fe;
}

/* Thread reply indicator */
.thread-indicator {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  padding: 4px 10px;
  border-radius: 8px;
  background: rgba(167, 139, 250, 0.08);
  border: 1px solid rgba(167, 139, 250, 0.15);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  color: #a78bfa;
  font-size: 12px;
  font-weight: 500;
}

.thread-indicator:hover {
  background: rgba(167, 139, 250, 0.15);
  border-color: rgba(167, 139, 250, 0.3);
}

.thread-indicator .thread-count {
  color: #a78bfa;
}

/* Welcome message title (h3) — larger and more prominent */
.welcome-message .markdown-content h3:first-child {
  font-size: 19px;
  font-weight: 700;
  margin: 0 0 8px;
  color: #f1f5f9;
}
</style>
