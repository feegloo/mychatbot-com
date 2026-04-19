<template>
  <div class="page upload-page">
    <div class="upload-hero">
      <h1 class="upload-title">chatrag.app</h1>
      <p class="upload-subtitle">Get answers with an AI chatbot using semantic search and RAG.</p>
    </div>

    <div class="upload-section">
      <h3 class="upload-heading">Upload your files</h3>
      <div
        class="dropzone upload-dropzone"
        :class="{ dragover }"
        style="cursor: pointer"
        @dragover.prevent="dragover = true"
        @dragleave.prevent="dragover = false"
        @drop.prevent="onDrop"
        @click="openFilePicker"
      >
        <div class="dropzone-icon">
          <svg
            width="40"
            height="40"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        </div>
        <p><strong>Drag and drop here</strong></p>
        <p class="dropzone-hint">PDF, images, .doc, other text files</p>
        <input ref="inputRef" type="file" multiple style="display: none" @change="onInputChange" />
      </div>

      <div class="upload-status-area">
        <div v-if="files.length" class="file-list" style="margin-top: 16px">
          <div v-for="file in files" :key="file.name" class="file-pill">
            {{ file.name }} - {{ (file.size / 1024 / 1024).toFixed(1) }} MB
          </div>
        </div>

        <p v-if="submitting" style="margin-top: 12px; color: #a78bfa; text-align: center">
          <UploadingDots />
        </p>

        <p v-if="error" style="color: #f87171; margin-top: 12px; text-align: center">{{ error }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { uploadFiles, saveConversationToken } from '../api'
import UploadingDots from '../components/UploadingDots.vue'

onMounted(() => {
  document.title = 'chatrag.app'
})

const router = useRouter()
const files = ref<File[]>([])
const dragover = ref(false)
const submitting = ref(false)
const error = ref('')
const inputRef = ref<HTMLInputElement | null>(null)

function openFilePicker() {
  inputRef.value?.click()
}

function onInputChange(event: Event) {
  const target = event.target as HTMLInputElement
  const allFiles = Array.from(target.files || [])
  const videoFiles = allFiles.filter((f) => f.type.startsWith('video/'))
  files.value = allFiles.filter((f) => !f.type.startsWith('video/'))
  if (videoFiles.length) error.value = 'Video files are not supported.'
  if (files.value.length) submit()
}

function onDrop(event: DragEvent) {
  dragover.value = false
  const allFiles = Array.from(event.dataTransfer?.files || [])
  const videoFiles = allFiles.filter((f) => f.type.startsWith('video/'))
  files.value = allFiles.filter((f) => !f.type.startsWith('video/'))
  if (videoFiles.length) error.value = 'Video files are not supported.'
  if (files.value.length) submit()
}

async function submit() {
  submitting.value = true
  error.value = ''

  try {
    const data = await uploadFiles(files.value)
    // Save owner password (persistent token) for this conversation
    if (data.ownerPassword) {
      saveConversationToken(data.conversationId, data.ownerPassword)
    }
    router.push(data.url)
  } catch (err: any) {
    error.value = err?.response?.data?.error || err?.message || 'Upload failed'
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.upload-page {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 0 32px 48px;
  overflow-y: auto;
}

.upload-hero {
  text-align: center;
  margin-bottom: 40px;
}

.upload-title {
  font-size: 2.4rem;
  margin: -10px 0 20px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #a78bfa;
}

.upload-subtitle {
  color: #64748b;
  margin: 0;
  font-size: 15px;
  line-height: 1.5;
}

.upload-section {
  width: 100%;
  max-width: 560px;
  position: relative;
}

.upload-status-area {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
}

.upload-heading {
  font-size: 1.1rem;
  margin: 0 0 14px;
  text-align: center;
}

.upload-dropzone {
  padding: 48px 36px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.dropzone-icon {
  color: #7c3aed;
  margin-bottom: 8px;
  opacity: 0.7;
  transition:
    opacity 0.25s ease,
    transform 0.25s ease;
}

.upload-dropzone p {
  margin: 4px 0;
}

.dropzone-hint {
  color: #64748b;
  font-size: 13px;
}

.upload-dropzone .button {
  margin-top: 8px;
}

@media (max-width: 768px) {
  .upload-page {
    padding: 24px 16px;
  }

  .upload-title {
    font-size: 1.8rem;
  }

  .upload-dropzone {
    padding: 32px 20px;
  }
}
</style>
