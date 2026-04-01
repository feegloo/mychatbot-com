<template>
  <div class="page">
    <div class="header" style="margin-bottom: 12px">
      <div>
        <h1 style="font-size: 1.1rem; margin: 0 0 4px 0">Conversation {{ conversationId }}</h1>
        <div style="display: flex; gap: 8px">
          <div class="status-badge">Status: {{ status.status }}</div>
          <div class="status-badge">Role: {{ status.role }}</div>
        </div>
      </div>
      <div style="display:flex; gap:12px">
        <button class="button secondary" @click="copyUrl">Copy shareable URL</button>
      </div>
    </div>

    <p v-if="status.errorMessage" style="color:#b91c1c; margin-bottom:16px">
      {{ status.errorMessage }}
    </p>

    <div class="grid grid-2">
      <section class="card">
        <h2>Chat</h2>

        <div style="margin-bottom: 12px">
          <textarea
            ref="questionInput"
            class="big-input"
            v-model="question"
            placeholder="Ask a question about the uploaded documents..."
          />
        </div>

        <div style="display:flex; gap:12px; margin-bottom:12px;">
          <button class="button" :disabled="asking || !question.trim()" @click="ask">
            {{ asking ? "Thinking..." : "Ask question" }}
          </button>
          <button class="button secondary" :disabled="asking || !question.trim()" @click="askStreaming">
            Live answer
          </button>
        </div>

        <p v-if="status.status !== 'ready'" style="margin-bottom:12px; color:#92400e">
          Conversation is currently {{ status.status }}. Asking will work after indexing finishes successfully.
        </p>

        <div class="chat-log" ref="chatContainer" style="flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; padding-right: 8px">
          <div v-for="(msg, index) in messages" :key="msg.id || index" class="message" :class="msg.role">
            <strong>{{ msg.role === 'user' ? 'You' : 'Assistant' }}</strong>
            <p style="white-space: pre-wrap">{{ msg.content }}</p>

            <div v-if="msg.citations?.length" class="sources">
              <div v-for="citation in msg.citations" :key="citation.chunkId + citation.text.slice(0,20)" class="source-card">
                <strong>{{ citation.fileName }}</strong>
                <div v-if="citation.section">Section: {{ citation.section }}</div>
                <div v-if="citation.page !== null && citation.page !== undefined">Page: {{ citation.page }}</div>
                <div style="margin-top:8px; white-space: pre-wrap; max-height: 300px; overflow-y: auto">{{ citation.text }}</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <aside class="card">
        <h2>Uploaded files</h2>
        <div>
          <span v-for="file in status.files" :key="file.id" class="file-pill">
            {{ cleanFileName(file.originalName) }}
          </span>
        </div>

        <div v-if="canUpload" style="margin-top:24px">
          <h2>Add more files</h2>
          <input ref="moreFilesInput" type="file" multiple @change="onMoreFilesChange" />
          <div class="file-list" v-if="moreFiles.length">
            <div v-for="file in moreFiles" :key="file.name" class="file-pill">
              {{ file.name }}
            </div>
          </div>
          <div style="margin-top:12px">
            <button class="button" :disabled="uploadingMore || !moreFiles.length" @click="uploadMore">
              {{ uploadingMore ? "Uploading..." : "Upload more files" }}
            </button>
          </div>
        </div>

        <div v-else style="margin-top:24px">
          <h2>Request upload access</h2>
          <input v-model="displayName" placeholder="Your name" style="width:100%; padding:10px; border-radius:12px; border:1px solid #cbd5e1;" />
          <div style="margin-top:12px">
            <button class="button" :disabled="requestingAccess || !displayName" @click="requestAccess">
              {{ requestingAccess ? "Requesting..." : "Ask for upload access" }}
            </button>
          </div>
          <p v-if="pendingRequestId" style="margin-top:10px">
            Request sent. Waiting for owner approval.
          </p>
        </div>

        <div v-if="status.role === 'owner' && status.accessRequests.length > 0" style="margin-top:24px">
          <h2>Pending access requests</h2>
          <div v-for="req in status.accessRequests" :key="req.id" class="source-card" style="margin-top:10px">
            <strong>{{ req.displayName }}</strong>
            <div>Status: {{ req.status }}</div>
            <div style="margin-top:10px" v-if="req.status === 'pending'">
              <button class="button" @click="approveRequest(req.id)">Approve editor access</button>
            </div>
          </div>
        </div>

        <h2 style="margin-top:24px">Suggested questions</h2>
        <div>
          <button
            v-for="q in status.suggestedQuestions"
            :key="q"
            class="question-pill"
            style="border:none; cursor:pointer"
            @click="question = q; questionInput?.focus()"
          >
            {{ q }}
          </button>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch, nextTick } from "vue";
import {
  askQuestion,
  getConversation,
  getStreamUrl,
  type ConversationStatus,
  type ChatMessage,
  uploadMoreFiles,
  requestUploadAccess,
  getUploadAccessRequest,
  approveUploadAccess,
  saveConversationToken
} from "../api";

const props = defineProps<{ conversationId: string }>();

const conversationId = props.conversationId;
const question = ref("");
const asking = ref(false);
const questionInput = ref<HTMLTextAreaElement | null>(null);
const chatContainer = ref<HTMLDivElement | null>(null);
const uploadingMore = ref(false);
const requestingAccess = ref(false);
const displayName = ref("");
const pendingRequestId = ref(localStorage.getItem(`pending-access-request:${conversationId}`) || "");
const moreFiles = ref<File[]>([]);
const moreFilesInput = ref<HTMLInputElement | null>(null);

const status = ref<ConversationStatus>({
  conversationId,
  status: "processing",
  role: "viewer",
  files: [],
  messages: [],
  suggestedQuestions: [],
  accessRequests: []
});
const messages = ref<ChatMessage[]>([]);

// Helper function to remove UUID prefix from filename (e.g., "uuid_filename.ext" -> "filename.ext")
const cleanFileName = (name: string): string => {
  const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_/i;
  return name.replace(uuidPattern, "");
};

const canUpload = computed(() => status.value.role === "owner" || status.value.role === "editor");

async function loadConversation() {
  const response = await getConversation(conversationId);
  status.value = response;
  messages.value = response.messages || [];
}

function scrollToBottom() {
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight;
  }
}

async function ask() {
  if (!question.value.trim()) return;
  if (status.value.status !== "ready") {
    await loadConversation();
    return;
  }

  asking.value = true;
  const currentQuestion = question.value;

  try {
    const response = await askQuestion(conversationId, currentQuestion);
    messages.value.push({ role: "user", content: currentQuestion });
    messages.value.push({
      role: "assistant",
      content: response.answer,
      citations: response.citations
    });
    question.value = "";
    await loadConversation();
  } finally {
    asking.value = false;
  }
}

async function askStreaming() {
  if (!question.value.trim()) return;
  if (status.value.status !== "ready") {
    await loadConversation();
    return;
  }

  asking.value = true;

  const currentQuestion = question.value;
  const assistantMessage: ChatMessage = {
    role: "assistant",
    content: "",
    citations: []
  };

  messages.value.push({ role: "user", content: currentQuestion });
  messages.value.push(assistantMessage);

  const source = new EventSource(getStreamUrl(conversationId, currentQuestion));

  source.addEventListener("token", (event: MessageEvent) => {
    const payload = JSON.parse(event.data);
    assistantMessage.content += payload.token;
  });

  source.addEventListener("citations", (event: MessageEvent) => {
    const payload = JSON.parse(event.data);
    assistantMessage.citations = payload.citations;
  });

  source.addEventListener("done", async () => {
    source.close();
    asking.value = false;
    question.value = "";
    await loadConversation();
  });

  source.addEventListener("error", () => {
    source.close();
    asking.value = false;
  });
}

function onMoreFilesChange(event: Event) {
  const target = event.target as HTMLInputElement;
  moreFiles.value = Array.from(target.files || []);
}

async function uploadMore() {
  if (!moreFiles.value.length) return;
  uploadingMore.value = true;
  try {
    await uploadMoreFiles(conversationId, moreFiles.value);
    moreFiles.value = [];
    if (moreFilesInput.value) moreFilesInput.value.value = "";
    await loadConversation();
  } finally {
    uploadingMore.value = false;
  }
}

async function requestAccess() {
  requestingAccess.value = true;
  try {
    const response = await requestUploadAccess(conversationId, displayName.value);
    pendingRequestId.value = response.requestId;
    localStorage.setItem(`pending-access-request:${conversationId}`, response.requestId);
  } finally {
    requestingAccess.value = false;
  }
}

async function pollAccessRequest() {
  if (!pendingRequestId.value) return;
  const response = await getUploadAccessRequest(conversationId, pendingRequestId.value);
  if (response.status === "approved" && response.editorToken) {
    saveConversationToken(conversationId, response.editorToken);
    localStorage.removeItem(`pending-access-request:${conversationId}`);
    pendingRequestId.value = "";
    await loadConversation();
  }
}

async function approveRequest(requestId: string) {
  await approveUploadAccess(conversationId, requestId);
  await loadConversation();
}

async function copyUrl() {
  await navigator.clipboard.writeText(window.location.href);
}

// Auto-scroll to bottom when messages update
watch(messages, async () => {
  await nextTick();
  scrollToBottom();
});

let intervalHandle: number | undefined;

onMounted(async () => {
  await loadConversation();
  await nextTick();
  scrollToBottom();

  intervalHandle = window.setInterval(async () => {
    await loadConversation();
    await pollAccessRequest();
  }, 2500);
});

onUnmounted(() => {
  if (intervalHandle !== undefined) {
    clearInterval(intervalHandle);
  }
});
</script>
