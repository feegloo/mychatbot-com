<template>
  <div class="page">
    <div class="header">
      <div>
        <h1 style="font-size: 2rem; margin: 0 0 6px; font-weight: 700; letter-spacing: -0.02em; color: #a78bfa">chatbotqa.app</h1>
        <p style="color: #64748b; margin: 0; font-size: 14px">Upload your own files, generate embeddings, then chat with a RAG bot at a unique shareable URL.</p>
      </div>
    </div>

    <div class="grid grid-2">
      <section>
        <h2>Upload files</h2>
        <div
          class="dropzone"
          :class="{ dragover }"
          @dragover.prevent="dragover = true"
          @dragleave.prevent="dragover = false"
          @drop.prevent="onDrop"
        >
          <p><strong>Drag and drop</strong> PDF, DOCX, TXT, MD, CSV, XLSX, HTML, XML, JSON, and other text-like files here.</p>
          <!-- <p>Future version: images and other unstructured files.</p> -->
          <input ref="inputRef" type="file" multiple @change="onInputChange" style="display:none" />
          <button class="button secondary" @click="openFilePicker">Choose files</button>
        </div>

        <div class="file-list" v-if="files.length">
          <div v-for="file in files" :key="file.name" class="file-pill">
            {{ file.name }} - {{ Math.round(file.size / 1024) }} KB
          </div>
        </div>

        <div style="margin-top:16px">
          <button class="button" :disabled="!files.length || submitting" @click="submit">
            {{ submitting ? "Uploading..." : "Upload files" }}
          </button>
        </div>

        <p v-if="error" style="color:#f87171; margin-top:12px">{{ error }}</p>
      </section>

      <aside>
        <h2 style="font-size: 1rem; margin: 8px 0 12px">How it works</h2>
        <ol style="color: #94a3b8; line-height: 1.8; padding-left: 20px; font-size: 14px">
          <li>Files are uploaded to the server.</li>
          <li>Node stores file metadata and creates a conversation URL.</li>
          <li>Python indexes content into Chroma using notebook mode or script mode.</li>
          <li>You open the chat and ask questions grounded in your uploaded files.</li>
        </ol>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { uploadFiles, saveConversationToken } from "../api";

onMounted(() => {
  document.title = "chatbotqa.app";
});

const router = useRouter();
const files = ref<File[]>([]);
const dragover = ref(false);
const submitting = ref(false);
const error = ref("");
const inputRef = ref<HTMLInputElement | null>(null);

function openFilePicker() {
  inputRef.value?.click();
}

function onInputChange(event: Event) {
  const target = event.target as HTMLInputElement;
  files.value = Array.from(target.files || []);
}

function onDrop(event: DragEvent) {
  dragover.value = false;
  files.value = Array.from(event.dataTransfer?.files || []);
}

async function submit() {
  submitting.value = true;
  error.value = "";

  try {
    const data = await uploadFiles(files.value);
    // Save owner password (persistent token) for this conversation
    if (data.ownerPassword) {
      saveConversationToken(data.conversationId, data.ownerPassword);
    }
    router.push(data.url);
  } catch (err: any) {
    error.value = err?.response?.data?.error || err?.message || "Upload failed";
  } finally {
    submitting.value = false;
  }
}
</script>
