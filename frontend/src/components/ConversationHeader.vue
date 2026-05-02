<template>
  <div class="header" style="margin-bottom: 12px; position: relative">
    <div
      class="conv-title-center"
      style="
        position: absolute;
        left: 0;
        right: 0;
        display: flex;
        justify-content: center;
        pointer-events: none;
      "
    >
      <div
        style="
          height: 30px;
          pointer-events: auto;
          max-width: 60%;
          min-width: 0;
          display: inline-flex;
          align-items: center;
          margin-left: 2px;
        "
      >
        <h1
          v-if="!editingName && conversationTitle"
          class="conv-title"
          :title="canUpload ? 'Click to rename' : ''"
          :style="canUpload ? 'cursor: pointer' : ''"
          @click="canUpload && startRename()"
        >
          {{ conversationTitle }}
        </h1>
        <div v-if="editingName" class="conv-title-input-wrap">
          <span ref="nameMeasure" class="conv-title-measure">{{ editNameValue || ' ' }}</span>
          <input
            ref="nameInput"
            v-model="editNameValue"
            class="conv-title-input"
            @keydown.enter="saveRename"
            @keydown.escape="editingName = false"
            @blur="saveRename"
          />
        </div>
      </div>
      <div class="header-badges" style="display: flex; gap: 8px">
        <div v-if="status.role === 'editor'" class="status-badge">role: {{ status.role }}</div>
      </div>
    </div>
    <div
      class="header-actions"
      style="
        display: flex;
        gap: 8px;
        align-items: center;
        flex-wrap: nowrap;
        margin-left: auto;
        z-index: 1;
      "
    >
      <div
        v-if="status.conversationThreadCount"
        class="conv-thread-count"
        @click="$emit('view-threads')"
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
        {{ status.conversationThreadCount }}
        {{ status.conversationThreadCount === 1 ? 'Reply' : 'Replies' }}
      </div>
      <VTooltip v-show="processing" :triggers="['hover']" placement="bottom">
        <div
          class="indexing-bar"
          role="status"
          aria-live="polite"
          :aria-label="processingStep || 'Processing files'"
        >
          <div class="indexing-spinner" aria-hidden="true"></div>
          <span class="sr-only">{{ processingStep || 'Processing files' }}</span>
        </div>
        <template #popper>
          <div class="indexing-tooltip">
            <div>{{ processingStep || 'Processing files…' }}</div>
            <div
              v-if="(parsedPages ?? 0) > 0 && (totalPages ?? 0) > 0"
              class="indexing-tooltip-pages"
            >
              {{ parsedPages }}/{{ totalPages }} pages
            </div>
          </div>
        </template>
      </VTooltip>
      <slot name="language-toggle"></slot>
      <slot name="auto-read-toggle"></slot>
      <button class="add-btn" @click="copyUrl">
        <template v-if="copied">Link copied!</template>
        <template v-else>
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M8 12H5a2 2 0 0 0-2 2v5a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5a2 2 0 0 0-2-2h-3" />
            <polyline points="12 3 12 15" />
            <polyline points="8 7 12 3 16 7" />
          </svg>
        </template>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { VTooltip } from 'floating-vue'
import { renameConversation, type ConversationStatus } from '../api'

const props = defineProps<{
  status: ConversationStatus
  conversationId: string
  conversationTitle: string
  canUpload: boolean
  processing?: boolean
  processingStep?: string
  parsedPages?: number
  totalPages?: number
}>()

const emit = defineEmits<{
  renamed: [name: string]
  reload: []
  'view-threads': []
}>()

const editingName = ref(false)
const editNameValue = ref('')
const nameInput = ref<HTMLInputElement | null>(null)
const nameMeasure = ref<HTMLSpanElement | null>(null)
const copied = ref(false)

async function startRename() {
  editingName.value = true
  editNameValue.value = props.status.displayName || props.conversationTitle
  await nextTick()
  nameInput.value?.select()
}

async function saveRename() {
  if (!editingName.value) return
  editingName.value = false
  const trimmed = editNameValue.value.trim()
  if (!trimmed || trimmed === props.status.displayName) return
  await renameConversation(props.conversationId, trimmed)
  emit('renamed', trimmed)
}

async function copyUrl() {
  await navigator.clipboard.writeText(window.location.href)
  copied.value = true
  setTimeout(() => {
    copied.value = false
  }, 2000)
}
</script>
