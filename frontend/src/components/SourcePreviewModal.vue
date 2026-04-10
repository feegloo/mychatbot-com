<template>
  <Teleport to="body">
    <div v-if="visible" class="source-modal-overlay" @click.self="$emit('close')">
      <div class="source-modal-content">
        <button class="source-modal-close" @click="$emit('close')">&times;</button>

        <div class="source-modal-header">
          <span class="source-modal-filename">{{ displayFileName }}</span>
          <span v-if="citation.page" class="source-modal-page">Page {{ citation.page }}</span>
        </div>

        <!-- PDF preview -->
        <div v-if="isPdf" class="source-modal-pdf">
          <iframe
            :src="pdfUrl"
            class="source-modal-iframe"
          ></iframe>
        </div>

        <!-- Source text quote -->
        <div class="source-modal-quote">
          <div class="source-modal-quote-label">Source text</div>
          <div class="source-modal-quote-text" v-html="linkify(citation.text)" />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { getDocumentUrl } from "../api";
import { cleanFileName, linkify } from "../utils/text";

const props = defineProps<{
  visible: boolean;
  citation: {
    fileName: string;
    chunkId: string;
    text: string;
    section?: string;
    page?: number | null;
    imageName?: string;
  };
  conversationId: string;
}>();

defineEmits<{
  close: [];
}>();

const displayFileName = computed(() => cleanFileName(props.citation.fileName));

const isPdf = computed(() =>
  props.citation.fileName.toLowerCase().endsWith(".pdf")
);

const pdfUrl = computed(() => {
  const base = getDocumentUrl(props.conversationId, props.citation.fileName);
  if (props.citation.page) {
    return `${base}#page=${props.citation.page}`;
  }
  return base;
});
</script>

<style scoped>
.source-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.source-modal-content {
  position: relative;
  width: min(900px, 92vw);
  max-height: 90vh;
  background: #1e293b;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  cursor: default;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.source-modal-close {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  background: #334155;
  color: #e2e8f0;
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
  transition: background 0.15s;
}

.source-modal-close:hover {
  background: #475569;
}

.source-modal-header {
  padding: 16px 48px 12px 16px;
  border-bottom: 1px solid #334155;
  display: flex;
  align-items: center;
  gap: 12px;
}

.source-modal-filename {
  font-weight: 600;
  color: #c4b5fd;
  font-size: 15px;
}

.source-modal-page {
  font-size: 13px;
  color: #94a3b8;
  background: #334155;
  padding: 2px 8px;
  border-radius: 4px;
}

.source-modal-pdf {
  flex: 1;
  min-height: 0;
}

.source-modal-iframe {
  width: 100%;
  height: 55vh;
  border: none;
  background: #fff;
}

.source-modal-quote {
  padding: 12px 16px 16px;
  border-top: 1px solid #334155;
  max-height: 200px;
  overflow-y: auto;
}

.source-modal-quote-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
  margin-bottom: 6px;
}

.source-modal-quote-text {
  font-size: 14px;
  color: #94a3b8;
  font-style: italic;
  white-space: pre-wrap;
  line-height: 1.5;
}
</style>
