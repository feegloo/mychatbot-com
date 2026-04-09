<template>
  <div class="message" :class="msg.role">
    <strong>{{ msg.role === 'user' ? 'You' : 'Assistant' }}</strong>
    <div v-if="msg.role === 'assistant' && !msg.content && asking" class="typing-dots">
      <span></span><span></span><span></span>
    </div>
    <div v-else-if="msg.role === 'assistant'" class="markdown-content" v-html="renderMarkdown(msg.content)"></div>
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

    <div v-if="msg.citations?.length" class="sources">
      <div class="source-card">
        <span class="citation-filename"><span style="color: #64748b; font-weight: 400">source: </span><strong style="color: #c4b5fd">{{ cleanFileName(msg.citations[activeTab].fileName) }}</strong></span>
        <div style="display: flex; flex-wrap: wrap; gap: 4px; margin: 6px 0 8px">
          <button
            v-for="(citation, cIdx) in msg.citations"
            :key="cIdx"
            class="citation-tab"
            :class="{ active: activeTab === cIdx }"
            @click="$emit('update:activeCitationIndex', cIdx)"
          >
            {{ getSectionLabel(citation) }}
          </button>
        </div>
        <!-- Show image for active image citation -->
        <div v-if="msg.citations[activeTab].imageName" class="citation-active-image" @click="openImage(resolveImageCitation(msg.citations[activeTab]))">
          <img :src="resolveImageCitation(msg.citations[activeTab]).url" :alt="msg.citations[activeTab].section || 'Image'" loading="lazy" />
        </div>
        <div style="white-space: pre-wrap; font-size: 14px; color: #94a3b8; font-style: italic;"
          v-html="linkify(msg.citations[activeTab].text)"
        />
      </div>
    </div>

    <ImageModal
      :visible="modalOpen"
      :src="modalSrc"
      :alt="modalAlt"
      @close="modalOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { marked } from "marked";
import DOMPurify from "dompurify";
import type { ChatMessage } from "../api";
import { getImageUrl } from "../api";
import { cleanFileName, linkify } from "../utils/text";
import ImageModal from "./ImageModal.vue";

marked.setOptions({
  breaks: true,
  gfm: true,
});

function renderMarkdown(content: string): string {
  const rawHtml = marked.parse(content, { async: false }) as string;
  return DOMPurify.sanitize(rawHtml);
}

const props = defineProps<{
  msg: ChatMessage;
  asking: boolean;
  activeCitationIndex: number;
  conversationId: string;
}>();

defineEmits<{
  'update:activeCitationIndex': [index: number];
}>();

const activeTab = computed(() => props.activeCitationIndex ?? 0);

// Image modal state
const modalOpen = ref(false);
const modalSrc = ref("");
const modalAlt = ref("");

type ImageCitationInfo = { url: string; section?: string; imageName: string };

function resolveImageCitation(citation: any): ImageCitationInfo {
  return {
    url: getImageUrl(props.conversationId, citation.imageName),
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

function getSectionLabel(citation: any): string {
  if (citation.imageName) {
    return citation.section || '🖼️ Image';
  }
  if (!citation.section) {
    if (citation.page !== null && citation.page !== undefined) {
      return 'Page ' + citation.page;
    }
    return 'Source';
  }
  
  // If section is short enough (real section header), use it as-is
  if (citation.section.length <= 30) {
    return citation.section;
  }
  
  // For long sections, try to extract the first meaningful phrase
  // Split by common sentence delimiters and take the first part
  const firstPhrase = citation.section.split(/[,;.!?]/)[0].trim();
  if (firstPhrase.length > 30) {
    // If still too long, take first N characters and add ellipsis
    return firstPhrase.substring(0, 30) + '…';
  }
  
  return firstPhrase || 'Source';
}
</script>

<style scoped>
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
