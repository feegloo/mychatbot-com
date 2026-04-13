<template>
  <Teleport to="body">
    <div v-if="visible" class="source-modal-overlay" @click.self="$emit('close')">
      <!-- Mobile close bar above content -->
      <div v-if="isMobile" class="source-modal-close-bar" @click="$emit('close')">
        <button class="source-modal-close-bar-x">&times;</button>
      </div>

      <div class="source-modal-content" :class="{ 'source-modal-content--text': !isPdf }">
        <button class="source-modal-close source-modal-close--desktop" @click="$emit('close')">&times;</button>

        <!-- PDF preview (desktop: inline iframe, mobile: inline object) -->
        <div v-if="isPdf && !isMobile" class="source-modal-pdf">
          <iframe
            :src="pdfUrl"
            class="source-modal-iframe"
          ></iframe>
        </div>

        <div v-if="isPdf && isMobile" class="source-modal-mobile-pdf">
          <object
            :data="pdfUrl"
            type="application/pdf"
            class="source-modal-mobile-object"
          >
            <iframe :src="pdfUrl" class="source-modal-mobile-object"></iframe>
          </object>
        </div>

        <!-- Source text quote at bottom on blue background (PDF only) -->
        <div v-if="isPdf && citation.text" class="source-modal-source-strip">
          <div class="source-modal-source-label">Source text<span v-if="citation.page">: Page {{ citation.page }}</span></div>
          <div class="source-modal-source-text" v-html="linkify(citation.text)" />
        </div>

        <!-- Source text quote (non-PDF only) -->
        <div v-if="!isPdf" class="source-modal-quote">
          <div class="source-modal-quote-label">Source text</div>
          <div class="source-modal-quote-text" v-html="linkify(citation.text)" />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { getStorageUrl } from "../api";
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

const isMobile = computed(() =>
  /iPhone|iPad|iPod|Android/i.test(navigator.userAgent)
);

const pdfUrl = computed(() => {
  const base = getStorageUrl(props.conversationId, props.citation.fileName);
  const fragment = props.citation.page
    ? `#page=${props.citation.page}&navpanes=0`
    : "#navpanes=0";
  return `${base}${fragment}`;
});

function openPdfInNewTab() {
  window.open(pdfUrl.value, "_blank", "noopener");
}
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

.source-modal-close-bar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 0 12px;
  z-index: 10;
  cursor: pointer;
}

.source-modal-close-bar-x {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.45);
  color: #e2e8f0;
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.source-modal-content {
  position: relative;
  width: min(900px, 92vw);
  height: calc(100vh - 20px);
  margin: 10px 0;
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
  top: 10px;
  right: 10px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.5);
  color: #e2e8f0;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2;
  transition: background 0.15s;
}

.source-modal-close:hover {
  background: rgba(0, 0, 0, 0.7);
}

.source-modal-pdf {
  flex: 1;
  min-height: 0;
}

.source-modal-iframe {
  width: 100%;
  height: 100%;
  border: none;
  background: #fff;
}

.source-modal-source-strip {
  padding: 12px 16px 14px;
  background: #3b5bdb;
  max-height: 140px;
  overflow-y: auto;
}

.source-modal-source-label {
  font-size: 11px;
  letter-spacing: 0.04em;
  color: rgba(255, 255, 255, 0.7);
  margin-bottom: 5px;
}

.source-modal-source-text {
  font-size: 12px;
  color: #fff;
  white-space: pre-wrap;
  line-height: 1.45;
}

.source-modal-quote {
  padding: 16px 20px 20px;
  flex: 1;
  min-height: 0;
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

/* Mobile: full-height inline PDF */
.source-modal-mobile-pdf {
  flex: 1;
  min-height: 0;
}

.source-modal-mobile-object {
  width: 100%;
  height: 100%;
  border: none;
  background: #fff;
}

.source-modal-content--text {
  height: auto;
  max-height: 50vh;
}

@media (max-width: 768px) {
  .source-modal-overlay {
    flex-direction: column;
  }

  .source-modal-close--desktop {
    display: none;
  }

  .source-modal-content {
    width: 100vw;
    height: calc(100vh - 44px);
    margin: 0;
    border-radius: 0;
  }

  .source-modal-content--text {
    height: auto;
    max-height: 60vh;
    width: 92vw;
    margin: auto;
    border-radius: 12px;
  }

  .source-modal-source-strip {
    max-height: 160px;
  }
}
</style>
