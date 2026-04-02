<template>
  <div class="message" :class="msg.role">
    <strong>{{ msg.role === 'user' ? 'You' : 'Assistant' }}</strong>
    <div v-if="msg.role === 'assistant' && !msg.content && asking" class="typing-dots">
      <span></span><span></span><span></span>
    </div>
    <p v-else style="white-space: pre-wrap">{{ msg.content }}</p>

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
        <div style="white-space: pre-wrap; font-size: 14px; color: #94a3b8; font-style: italic;"
          v-html="linkify(msg.citations[activeTab].text)"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { ChatMessage } from "../api";
import { cleanFileName, linkify } from "../utils/text";

const props = defineProps<{
  msg: ChatMessage;
  asking: boolean;
  activeCitationIndex: number;
}>();

defineEmits<{
  'update:activeCitationIndex': [index: number];
}>();

const activeTab = computed(() => props.activeCitationIndex ?? 0);

function getSectionLabel(citation: any): string {
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
