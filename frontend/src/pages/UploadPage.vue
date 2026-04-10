<template>
  <div class="page">
    <div class="header">
      <div>
        <h1 style="font-size: 2rem; margin: 0 0 6px; font-weight: 700; letter-spacing: -0.02em; color: #a78bfa">chatrag.app</h1>
        <p style="color: #64748b; margin: 0; font-size: 14px">Upload pdf or text files, chat with AI over files with semantic search (RAG), get answers.</p>
      </div>
    </div>

    <div class="grid grid-2">
      <section>
        <h3>Upload files</h3>
        <div
          class="dropzone"
          :class="{ dragover }"
          @dragover.prevent="dragover = true"
          @dragleave.prevent="dragover = false"
          @drop.prevent="onDrop"
        >
          <p><strong>Drag and drop</strong> your files here (PDF, DOCX, CSV, other text files)</p>
          <!-- <p>Future version: images and other unstructured files.</p> -->
          <input ref="inputRef" type="file" multiple @change="onInputChange" style="display:none" />
          <button class="button secondary" @click="openFilePicker">Choose files</button>
        </div>

        <div class="file-list" v-if="files.length">
          <div v-for="file in files" :key="file.name" class="file-pill">
            {{ file.name }} - {{ Math.round(file.size / 1024) }} KB
          </div>
        </div>

        <p v-if="submitting" style="margin-top:12px; color:#a78bfa">Uploading...</p>

        <p v-if="error" style="color:#f87171; margin-top:12px">{{ error }}</p>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { uploadFiles, saveConversationToken } from "../api";

onMounted(() => {
  document.title = "chatrag.app";
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
  if (files.value.length) submit();
}

function onDrop(event: DragEvent) {
  dragover.value = false;
  files.value = Array.from(event.dataTransfer?.files || []);
  if (files.value.length) submit();
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
