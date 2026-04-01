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
        <h3 style="margin: 4px 0 8px; font-size: 0.95rem">Chat</h3>

        <p v-if="status.status !== 'ready'" style="margin-bottom:12px; color:#92400e">
          Conversation is currently {{ status.status }}. Asking will work after indexing finishes successfully.
        </p>

        <div class="chat-log" ref="chatContainer" style="flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; padding-right: 8px">
          <div style="flex: 1"></div>
          <div v-for="(msg, index) in messages" :key="msg.id || index" class="message" :class="msg.role">
            <strong>{{ msg.role === 'user' ? 'You' : 'Assistant' }}</strong>
            <div v-if="msg.role === 'assistant' && !msg.content && asking" class="typing-dots">
              <span></span><span></span><span></span>
            </div>
            <p v-else style="white-space: pre-wrap">{{ msg.content }}</p>

            <div v-if="msg.citations?.length" class="sources">
              <div class="source-card">
                <span class="citation-filename"><span style="color: #94a3b8; font-weight: 400">source: </span><strong>{{ cleanFileName(msg.citations[activeCitationTab[index] ?? 0].fileName) }}</strong></span>
                <div style="display: flex; flex-wrap: wrap; gap: 4px; margin: 6px 0 8px">
                  <button
                    v-for="(citation, cIdx) in msg.citations"
                    :key="cIdx"
                    class="citation-tab"
                    :class="{ active: (activeCitationTab[index] ?? 0) === cIdx }"
                    @click="activeCitationTab[index] = cIdx"
                  >
                    {{ citation.section || (citation.page !== null && citation.page !== undefined ? 'Page ' + citation.page : 'Source ' + (cIdx + 1)) }}
                  </button>
                </div>
                <div style="white-space: pre-wrap; font-size: 12px">
                  {{ msg.citations[activeCitationTab[index] ?? 0].text }}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="chat-input-bar">
          <button
            v-show="false"
            class="live-toggle"
            :class="{ active: liveMode }"
            @click="liveMode = !liveMode"
            title="Toggle live streaming"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 3h6l1 7H8L9 3z"/>
              <path d="M8 10l-1.5 11h11L16 10"/>
              <line x1="12" y1="3" x2="12" y2="0.5"/>
            </svg>
            Live
          </button>
          <textarea
            ref="questionInput"
            class="chat-textarea"
            v-model="question"
            placeholder="Ask a question..."
            rows="1"
            @input="autoResize"
            @keydown.enter.exact.prevent="submitQuestion"
          ></textarea>
          <button
            class="send-btn"
            :disabled="asking || !question.trim()"
            @click="submitQuestion"
          >
            <svg v-if="!asking" width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
            <div v-else class="typing-dots" style="margin:0"><span></span><span></span><span></span></div>
          </button>
        </div>
      </section>

      <aside class="card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px">
          <h3 style="margin: 0; font-size: 0.95rem">Uploaded files</h3>
          <button v-if="canUpload" class="button" style="padding: 6px 12px; font-size: 13px" @click="moreFilesInput?.click()">
            + Add
          </button>
        </div>
        <div style="margin-bottom: 16px">
          <span v-for="file in status.files" :key="file.id" class="file-pill" style="font-size: 13px">
            {{ cleanFileName(file.originalName) }}
          </span>
        </div>

        <input ref="moreFilesInput" type="file" multiple @change="onMoreFilesChange" style="display:none" />
        <div v-if="moreFiles.length" style="margin-bottom: 12px">
          <div class="file-list">
            <div v-for="file in moreFiles" :key="file.name" class="file-pill" style="font-size: 13px">
              {{ file.name }}
            </div>
          </div>
          <button class="button" style="margin-top: 8px; font-size: 13px; padding: 6px 12px" :disabled="uploadingMore || !moreFiles.length" @click="uploadMore">
            {{ uploadingMore ? "Uploading..." : "Upload" }}
          </button>
        </div>

        <div v-if="!canUpload" style="margin-bottom: 16px">
          <h3 style="margin: 0 0 8px 0; font-size: 0.95rem">Request upload access</h3>
          <div v-if="pendingRequestId">
            <p style="margin: 0; font-size: 12px; color: #64748b">
              Request sent. Waiting for owner approval...
            </p>
          </div>
          <div v-else>
            <input v-model="displayName" placeholder="Your name" style="width:100%; padding:8px; border-radius:8px; border:1px solid #cbd5e1; font-size: 13px" />
            <button class="button" style="margin-top: 8px; font-size: 13px; padding: 6px 12px; width: 100%" :disabled="requestingAccess || !displayName" @click="requestAccess">
              {{ requestingAccess ? "Requesting..." : "Request access" }}
            </button>
          </div>
        </div>

        <div v-if="status.role === 'owner' && status.accessRequests.length > 0" style="margin-bottom: 16px; padding-top: 12px; border-top: 1px solid #e2e8f0">
          <h3 style="margin: 0 0 8px 0; font-size: 0.95rem">Access requests</h3>
          <div v-for="req in status.accessRequests" :key="req.id" style="font-size: 13px; margin-bottom: 8px; padding: 8px; background: #f1f5f9; border-radius: 8px">
            <div style="font-weight: 500">{{ req.displayName }}</div>
            <div style="color: #64748b; font-size: 12px">{{ req.status }}</div>
            <button v-if="req.status === 'pending'" class="button" style="margin-top: 6px; font-size: 12px; padding: 4px 8px" @click="approveRequest(req.id)">Approve</button>
          </div>
        </div>

        <div style="padding-top: 12px; border-top: 1px solid #e2e8f0">
          <h3 style="margin: 0 0 10px 0; font-size: 0.95rem">Suggested questions</h3>
          <div>
            <button
              v-for="q in status.suggestedQuestions"
              :key="q"
              class="question-pill"
              style="border:none; cursor:pointer; font-size: 12px; padding: 6px 10px; margin: 4px 0"
              @click="question = q; questionInput?.focus()"
            >
              {{ q }}
            </button>
          </div>
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
const liveMode = ref(false);
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
const activeCitationTab = ref<Record<number, number>>({});

// Helper function to remove UUID prefix from filename (e.g., "uuid_filename.ext" -> "filename.ext")
const cleanFileName = (name: string): string => {
  const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_/i;
  return name.replace(uuidPattern, "");
};

const canUpload = computed(() => status.value.role === "owner" || status.value.role === "editor");

async function loadConversation() {
  const response = await getConversation(conversationId);
  status.value = response;
  // Don't overwrite messages while asking — local optimistic messages would be wiped
  if (!asking.value) {
    messages.value = response.messages || [];
  }
}

function scrollToBottom() {
  if (chatContainer.value) {
    // Force a reflow
    const scrollHeight = chatContainer.value.scrollHeight;
    chatContainer.value.scrollTop = scrollHeight;
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
  question.value = "";
  messages.value.push({ role: "user", content: currentQuestion });

  // Add placeholder for assistant response (replaces 3-dot indicator in-place)
  const assistantPlaceholder: ChatMessage = { role: "assistant", content: "" };
  messages.value.push(assistantPlaceholder);

  try {
    const response = await askQuestion(conversationId, currentQuestion);
    // Update in-place instead of pushing new message
    assistantPlaceholder.content = response.answer;
    assistantPlaceholder.citations = response.citations;
    await loadConversation();
  } finally {
    asking.value = false;
  }
}

function submitQuestion() {
  if (asking.value || !question.value.trim()) return;
  if (liveMode.value) {
    askStreaming();
  } else {
    ask();
  }
  // Reset textarea height
  if (questionInput.value) {
    questionInput.value.style.height = 'auto';
  }
}

function autoResize(e: Event) {
  const el = e.target as HTMLTextAreaElement;
  el.style.height = 'auto';
  el.style.height = el.scrollHeight + 'px';
}

async function askStreaming() {
  if (!question.value.trim()) return;
  if (status.value.status !== "ready") {
    await loadConversation();
    return;
  }

  asking.value = true;

  const currentQuestion = question.value;
  question.value = "";

  messages.value.push({ role: "user", content: currentQuestion });
  messages.value.push({ role: "assistant", content: "", citations: [] });

  // Get the reactive proxy so mutations trigger Vue updates
  const reactiveMsg = messages.value[messages.value.length - 1];

  const source = new EventSource(getStreamUrl(conversationId, currentQuestion));

  source.addEventListener("token", (event: MessageEvent) => {
    const payload = JSON.parse(event.data);
    reactiveMsg.content += payload.token;
    nextTick(() => scrollToBottom());
  });

  source.addEventListener("citations", (event: MessageEvent) => {
    const payload = JSON.parse(event.data);
    reactiveMsg.citations = payload.citations;
  });

  source.addEventListener("done", async () => {
    source.close();
    asking.value = false;
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
  if (response.status === "approved" && response.editorPassword) {
    saveConversationToken(conversationId, response.editorPassword);
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
let prevMessageCount = 0;
watch(() => messages.value.length, async (newLen) => {
  if (newLen > prevMessageCount) {
    await nextTick();
    setTimeout(() => scrollToBottom(), 0);
  }
  prevMessageCount = newLen;
});

let intervalHandle: number | undefined;

onMounted(async () => {
  await loadConversation();
  await nextTick();
  setTimeout(() => scrollToBottom(), 100);

  intervalHandle = window.setInterval(async () => {
    await loadConversation();
    await pollAccessRequest();
  }, 1000);
});

onUnmounted(() => {
  if (intervalHandle !== undefined) {
    clearInterval(intervalHandle);
  }
});
</script>
