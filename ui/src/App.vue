<template>
  <div>
    <aside class="menu" aria-label="Left menu" data-testid="menu-column"></aside>
    <main class="content" aria-label="Main content" data-testid="content-column">
      <HomeHero />

      <form class="upload-form" @submit.prevent="handleUpload">
        <label class="upload-label" for="cloud-function-files">Choose files</label>
        <input
          id="cloud-function-files"
          data-testid="cloud-function-file-input"
          type="file"
          multiple
          @change="handleFilesChanged"
        />
        <button
          data-testid="cloud-function-upload-button"
          class="upload-button"
          type="submit"
          :disabled="isUploading || selectedFiles.length === 0"
        >
          {{ isUploading ? 'Uploading...' : 'Upload via Cloud Function' }}
        </button>
      </form>

      <p v-if="uploadError" class="upload-error" data-testid="cloud-function-upload-error">
        {{ uploadError }}
      </p>

      <a
        v-if="conversationUrl"
        class="conversation-link"
        :href="conversationUrl"
        data-testid="cloud-function-conversation-url"
      >
        {{ conversationUrl }}
      </a>

      <p class="hello-world-message" data-testid="hello-world-message">{{ helloMessage }}</p>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import * as Sentry from '@sentry/vue'
import HomeHero from '@frontend-home-hero'

const helloMessage = ref('')
const selectedFiles = ref<File[]>([])
const isUploading = ref(false)
const uploadError = ref('')
const conversationUrl = ref('')

const cloudFunctionUploadUrl =
  import.meta.env.VITE_CLOUD_FUNCTION_UPLOAD_URL ||
  'https://us-central1-your-project.cloudfunctions.net/chatrag-upload/upload'

onMounted(async () => {
  const res = await fetch('/api2/hello-world')
  const data = await res.json()
  helloMessage.value = data.message
})

function handleFilesChanged(event: Event) {
  const input = event.target as HTMLInputElement
  selectedFiles.value = input.files ? Array.from(input.files) : []
  uploadError.value = ''
  conversationUrl.value = ''
}

async function handleUpload() {
  if (!selectedFiles.value.length || isUploading.value) return

  uploadError.value = ''
  conversationUrl.value = ''
  isUploading.value = true

  const traceId = createTraceId()

  try {
    await Sentry.startNewTrace(async () => {
      await Sentry.startSpan(
        {
          name: 'ui.upload.via_cloud_function',
          op: 'ui.action.upload',
          attributes: {
            'chatrag.trace_id': traceId,
            'upload.file_count': selectedFiles.value.length,
          },
          forceTransaction: true,
        },
        async () => {
          Sentry.setTag('trace_id', traceId)
          Sentry.addBreadcrumb({
            category: 'upload',
            level: 'debug',
            message: `Upload journey started: ${traceId}`,
          })
          Sentry.captureMessage(`Upload journey started [${traceId}]`, 'debug')

          const formData = new FormData()
          for (const file of selectedFiles.value) {
            formData.append('files', file)
          }

          const traceData = Sentry.getTraceData()
          const headers = new Headers()
          headers.set('x-trace-id', traceId)
          if (traceData['sentry-trace']) {
            headers.set('sentry-trace', traceData['sentry-trace'])
          }
          if (traceData.baggage) {
            headers.set('baggage', traceData.baggage)
          }

          const response = await fetch(cloudFunctionUploadUrl, {
            method: 'POST',
            body: formData,
            headers,
          })

          const payload = (await response.json()) as {
            url?: string
            error?: string
          }

          if (!response.ok || !payload.url) {
            uploadError.value = payload.error || 'Upload failed. Please try again.'
            Sentry.captureMessage(`Upload journey failed [${traceId}]`, 'error')
            return
          }

          conversationUrl.value = payload.url
          Sentry.captureMessage(`Upload journey accepted [${traceId}]`, 'info')
          window.location.assign(payload.url)
        }
      )
    })
  } catch (error) {
    uploadError.value = error instanceof Error ? error.message : 'Upload failed. Please try again.'
    Sentry.captureException(error, {
      tags: { trace_id: traceId },
      extra: { traceId },
    })
  } finally {
    isUploading.value = false
  }
}

function createTraceId(): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
  const bytes = new Uint8Array(12)
  crypto.getRandomValues(bytes)
  let result = ''
  for (let i = 0; i < bytes.length; i++) {
    result += alphabet[bytes[i] % alphabet.length]
  }
  return result
}
</script>

<style lang="css" scoped>
#app :deep(> div) {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  min-height: 100vh;
}

.menu {
  background: var(--menu-column-bg);
}

.content {
  background: var(--content-column-bg);
  overflow: auto;
}

.content > * {
  min-height: 100%;
}

.upload-form {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin: 16px auto;
  max-width: 960px;
  padding: 12px;
  background: #ffffff;
  border: 1px solid #d4d4d8;
  border-radius: 10px;
}

.upload-label {
  font-size: 14px;
  color: #111827;
  font-weight: 600;
}

.upload-button {
  border: none;
  border-radius: 8px;
  padding: 10px 14px;
  background: #0f766e;
  color: #ffffff;
  font-weight: 600;
  cursor: pointer;
}

.upload-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.upload-error {
  color: #b91c1c;
  font-size: 14px;
  margin: 0 auto 12px;
  max-width: 960px;
}

.conversation-link {
  display: block;
  margin: 0 auto 12px;
  max-width: 960px;
  color: #0f766e;
}

@media (max-width: 768px) {
  #app :deep(> div) {
    grid-template-columns: 1fr;
    grid-template-rows: 120px minmax(0, 1fr);
  }

  .menu {
    min-height: 120px;
  }
}
</style>
