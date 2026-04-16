<template>
  <aside class="card sidebar-card">
    <input ref="moreFilesInput" type="file" multiple @change="onMoreFilesChange" style="display:none" />
    <div v-if="moreFiles.length || uploadError" style="margin-bottom: 12px">
      <p v-if="uploadError" style="margin: 0 0 8px 0; font-size: 13px; color: #fbbf24">{{ uploadError }}</p>
      <template v-if="moreFiles.length">
        <div style="margin-bottom: 4px">
          <span v-for="file in moreFiles" :key="file.name" style="font-size: 13px; color: #cbd5e1; display: block">
            {{ file.name }}
          </span>
        </div>
        <span v-if="uploadingMore" style="font-size: 13px; color: #a78bfa">Uploading...</span>
      </template>
    </div>

    <div v-if="loaded && !canUpload" style="margin-bottom: 16px">
      <h3 style="margin: 0 0 8px 0; font-size: 0.95rem">Request upload access</h3>
      <div v-if="pendingRequestId">
        <p style="margin: 0; font-size: 12px; color: #64748b">
          Request sent. Waiting for owner approval...
        </p>
      </div>
      <div v-else>
        <input v-model="displayName" placeholder="Your name" style="width:100%; padding:8px; border-radius:8px; border:1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.04); color: #e2e8f0; font-size: 13px" />
        <button class="button" style="margin-top: 8px; font-size: 13px; padding: 6px 12px; width: 100%" :disabled="requestingAccess || !displayName" @click="requestAccess">
          {{ requestingAccess ? "Requesting..." : "Request access" }}
        </button>
      </div>
    </div>

    <div v-if="status.role === 'owner' && status.accessRequests.length > 0" style="margin-bottom: 16px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.06)">
      <h3 style="margin: 0 0 8px 0; font-size: 0.95rem">Access requests</h3>
      <div v-for="req in status.accessRequests" :key="req.id" style="font-size: 13px; margin-bottom: 8px; padding: 8px; background: rgba(255,255,255,0.04); border-radius: 8px; border: 1px solid rgba(255,255,255,0.06)">
        <div style="font-weight: 500">{{ req.displayName }}</div>
        <div style="color: #64748b; font-size: 12px">{{ req.status }}</div>
        <button v-if="req.status === 'pending'" class="button" style="margin-top: 6px; font-size: 12px; padding: 4px 8px" @click="approveRequest(req.id)">Approve</button>
      </div>
    </div>

    <div v-if="!hasWelcomeMessage" style="padding-top: 2px">
      <h3 style="margin: 0 0 2px 0; font-size: 0.95rem">Suggested prompts</h3>
      <div>
        <button
          v-for="q in status.suggestedQuestions"
          :key="q"
          class="question-pill"
          style="border:none; cursor:pointer; font-size: 12px; padding: 6px 10px; margin: 4px 0 8px 0; display: inline-flex; align-items: center;"
          @click="$emit('select-question', q)"
        >
          {{ q }}
        </button>
        <div v-if="status.status === 'processing'" style="display: flex; justify-content: center; margin: 8px 0 0 0"><div class="typing-dots"><span></span><span></span><span></span></div></div>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref } from "vue";
import {
  type ConversationStatus,
  uploadMoreFiles,
  requestUploadAccess,
  getUploadAccessRequest,
  approveUploadAccess,
  saveConversationToken
} from "../api";

const props = defineProps<{
  status: ConversationStatus;
  conversationId: string;
  canUpload: boolean;
  loaded: boolean;
  hasWelcomeMessage: boolean;
}>();

const emit = defineEmits<{
  reload: [];
  'select-question': [question: string];
}>();

const uploadingMore = ref(false);
const uploadError = ref("");
const moreFiles = ref<File[]>([]);
const moreFilesInput = ref<HTMLInputElement | null>(null);
const requestingAccess = ref(false);
const displayName = ref("");
const pendingRequestId = ref(localStorage.getItem(`pending-access-request:${props.conversationId}`) || "");



function onMoreFilesChange(event: Event) {
  const target = event.target as HTMLInputElement;
  moreFiles.value = Array.from(target.files || []);
  uploadError.value = "";
  if (moreFiles.value.length) {
    uploadMore();
  }
}

async function uploadMore() {
  if (!moreFiles.value.length) return;
  uploadingMore.value = true;
  try {
    await uploadMoreFiles(props.conversationId, moreFiles.value);
    moreFiles.value = [];
    if (moreFilesInput.value) moreFilesInput.value.value = "";
    emit("reload");
  } catch (err: any) {
    if (err.response?.status === 409) {
      const names = (err.response.data?.duplicates || []).join(", ");
      uploadError.value = names ? `File ${names} already uploaded` : "File already uploaded";
      moreFiles.value = [];
      if (moreFilesInput.value) moreFilesInput.value.value = "";
    } else {
      throw err;
    }
  } finally {
    uploadingMore.value = false;
  }
}

async function requestAccess() {
  requestingAccess.value = true;
  try {
    const response = await requestUploadAccess(props.conversationId, displayName.value);
    pendingRequestId.value = response.requestId;
    localStorage.setItem(`pending-access-request:${props.conversationId}`, response.requestId);
  } finally {
    requestingAccess.value = false;
  }
}

async function pollAccessRequest() {
  if (!pendingRequestId.value) return;
  const response = await getUploadAccessRequest(props.conversationId, pendingRequestId.value);
  if (response.status === "approved" && response.editorPassword) {
    saveConversationToken(props.conversationId, response.editorPassword);
    localStorage.removeItem(`pending-access-request:${props.conversationId}`);
    pendingRequestId.value = "";
    emit("reload");
  }
}

async function approveRequest(requestId: string) {
  await approveUploadAccess(props.conversationId, requestId);
  emit("reload");
}

defineExpose({ pollAccessRequest, triggerUpload });

function triggerUpload() {
  moreFilesInput.value?.click();
}
</script>


