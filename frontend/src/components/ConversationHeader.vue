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
      <div style="height: 30px; pointer-events: auto; max-width: 60%; min-width: 0; display: inline-flex;align-items: center;margin-left: 2px;">
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
      <div
        v-if="processing"
        class="indexing-bar"
        role="status"
        aria-live="polite"
        :aria-label="processingStep || 'Processing files'"
        :title="processingStep || 'Processing files…'"
      >
        <div class="indexing-spinner" aria-hidden="true"></div>
        <span class="sr-only">{{ processingStep || 'Processing files' }}</span>
      </div>
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
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
          </svg>
        </template>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { AxiosError } from 'axios'
import { renameConversation, uploadMoreFiles, type ConversationStatus } from '../api'

const props = defineProps<{
  status: ConversationStatus
  conversationId: string
  conversationTitle: string
  canUpload: boolean
  processing?: boolean
  processingStep?: string
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
const fileInput = ref<HTMLInputElement | null>(null)
const selectedFiles = ref<File[]>([])
const uploading = ref(false)
const uploadError = ref('')

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

function _onFilesChange(event: Event) {
  const target = event.target as HTMLInputElement
  selectedFiles.value = Array.from(target.files || [])
  uploadError.value = ''
}

async function _uploadFiles() {
  if (!selectedFiles.value.length) return
  uploading.value = true
  uploadError.value = ''
  try {
    await uploadMoreFiles(props.conversationId, selectedFiles.value)
    selectedFiles.value = []
    if (fileInput.value) fileInput.value.value = ''
    emit('reload')
  } catch (err: unknown) {
    if (err instanceof AxiosError && err.response?.status === 409) {
      const names = ((err.response.data as Record<string, unknown>)?.duplicates as string[] || []).join(', ')
      uploadError.value = names ? `File ${names} already uploaded` : 'File already uploaded'
      selectedFiles.value = []
      if (fileInput.value) fileInput.value.value = ''
    } else {
      uploadError.value = 'Upload failed'
    }
  } finally {
    uploading.value = false
  }
}

async function copyUrl() {
  await navigator.clipboard.writeText(window.location.href)
  copied.value = true
  setTimeout(() => {
    copied.value = false
  }, 2000)
}

function triggerUpload() {
  fileInput.value?.click()
}

defineExpose({ triggerUpload })
</script>
