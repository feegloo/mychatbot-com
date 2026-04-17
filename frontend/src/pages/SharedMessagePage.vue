<template>
  <div class="page shared-message-page">
    <div v-if="loading" class="shared-loading">Loading…</div>
    <div v-else-if="error" class="shared-error">{{ error }}</div>
    <template v-else-if="message">
      <div class="shared-header">
        <span class="shared-label">Shared answer</span>
        <span v-if="message.displayName" class="shared-conv-name">{{ message.displayName }}</span>
        <router-link :to="`/c/${message.conversationId}`" class="shared-open-link">Open full conversation →</router-link>
      </div>
      <div class="shared-message-container">
        <ChatMessageItem
          :msg="message"
          :asking="false"
          :conversationId="message.conversationId"
          :isWelcome="sharedIsWelcome"
          :files="sharedFiles"
          @select-question="replyText = $event; startThread()"
        />
      </div>

      <!-- Thread replies section -->
      <div v-if="threads.length" class="threads-section">
        <div class="threads-header">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          {{ totalReplies }} {{ totalReplies === 1 ? 'reply' : 'replies' }} in {{ threads.length }} {{ threads.length === 1 ? 'thread' : 'threads' }}
        </div>
        <div v-for="thread in threads" :key="thread.conversationId" class="thread-bubble">
          <router-link :to="`/c/${thread.conversationId}`" class="thread-link">
            <span class="thread-user">{{ thread.lastUserId === getUserId() ? 'YOU' : `user${thread.lastUserId}` }}</span>
            <span class="thread-count">{{ thread.messageCount }} {{ thread.messageCount === 1 ? 'message' : 'messages' }}</span>
            <span class="thread-arrow">→</span>
          </router-link>
        </div>
      </div>

      <!-- Reply input to start a new thread -->
      <div class="thread-reply-bar">
        <textarea
          ref="replyInput"
          class="thread-reply-textarea"
          v-model="replyText"
          placeholder="Reply to start a new thread..."
          rows="1"
          @input="autoResize"
          @keydown.enter.exact.prevent="startThread"
        ></textarea>
        <button
          class="thread-send-btn"
          :disabled="creatingThread || !replyText.trim()"
          @click="startThread"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
        </button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch, computed } from "vue";
import { useRouter } from "vue-router";
import { getSharedMessage, getMessageThreads, createThread, saveConversationToken, type SharedMessage, type ThreadSummary } from "../api";
import { getUserId } from "../utils/fingerprint";
import ChatMessageItem from "../components/ChatMessage.vue";

const props = defineProps<{ messageId: string }>();
const router = useRouter();

const message = ref<SharedMessage | null>(null);
const loading = ref(true);
const error = ref("");
const threads = ref<ThreadSummary[]>([]);
const replyText = ref("");
const replyInput = ref<HTMLTextAreaElement | null>(null);
const creatingThread = ref(false);

const totalReplies = computed(() => threads.value.reduce((sum, t) => sum + t.messageCount, 0));
const sharedIsWelcome = computed(() => !!message.value?.uploadedFileNames?.length);
const sharedFiles = computed(() => message.value?.files);

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const [msg, threadData] = await Promise.all([
      getSharedMessage(props.messageId),
      getMessageThreads(props.messageId)
    ]);
    message.value = msg;
    threads.value = threadData.threads;
    document.title = `${msg.displayName || "Shared answer"} | chatrag.app`;
  } catch {
    error.value = "Message not found";
  } finally {
    loading.value = false;
  }
}

async function startThread() {
  if (!replyText.value.trim() || creatingThread.value) return;
  const userId = getUserId();
  if (!userId) {
    error.value = "Could not identify your browser. Please reload.";
    return;
  }
  creatingThread.value = true;
  const pendingQuestion = replyText.value.trim();
  try {
    const result = await createThread(props.messageId, userId);
    // Save the owner token so user can continue chatting
    saveConversationToken(result.conversationId, result.ownerPassword);
    // Navigate to the new thread conversation with the pending question
    router.push({ path: `/c/${result.conversationId}`, state: { pendingQuestion } });
  } catch (err: any) {
    error.value = err?.response?.data?.error || "Failed to create thread";
  } finally {
    creatingThread.value = false;
  }
}

function autoResize(e: Event) {
  const el = e.target as HTMLTextAreaElement;
  el.style.height = "auto";
  el.style.height = el.scrollHeight + "px";
}

onMounted(load);
watch(() => props.messageId, load);
</script>

<style scoped>
.shared-message-page {
  max-width: 800px;
  justify-content: flex-start;
  gap: 16px;
  overflow-y: auto;
}

.shared-header {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.shared-label {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
  font-weight: 600;
}

.shared-conv-name {
  font-size: 14px;
  color: #cbd5e1;
}

.shared-open-link {
  margin-left: auto;
  font-size: 13px;
  color: #a78bfa;
  text-decoration: none;
  transition: color 0.15s;
}

@media (hover: hover) {
  .shared-open-link:hover {
    color: #c4b5fd;
  }
}

.shared-message-container {
  width: 100%;
}

.shared-loading,
.shared-error {
  color: #94a3b8;
  font-size: 15px;
  text-align: center;
  margin-top: 40px;
}

.shared-error {
  color: #f87171;
}

/* Thread replies section */
.threads-section {
  width: 100%;
  margin-top: 8px;
}

.threads-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #a78bfa;
  font-weight: 600;
  margin-bottom: 8px;
}

.thread-bubble {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  padding: 8px 14px;
  margin-bottom: 6px;
  transition: background 0.15s;
}

.thread-bubble:hover {
  background: rgba(255, 255, 255, 0.07);
}

.thread-link {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
  color: inherit;
}

.thread-user {
  font-size: 13px;
  font-weight: 600;
  color: #60a5fa;
}

.thread-count {
  font-size: 12px;
  color: #64748b;
}

.thread-arrow {
  margin-left: auto;
  color: #64748b;
  font-size: 14px;
}

/* Reply bar */
.thread-reply-bar {
  width: 100%;
  display: flex;
  gap: 8px;
  align-items: flex-end;
  margin-top: 12px;
}

.thread-reply-textarea {
  flex: 1;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 10px;
  padding: 10px 14px;
  color: #e2e8f0;
  font-size: 14px;
  resize: none;
  min-height: 40px;
  max-height: 120px;
  outline: none;
  transition: border-color 0.15s;
  font-family: inherit;
}

.thread-reply-textarea:focus {
  border-color: #a78bfa;
}

.thread-reply-textarea::placeholder {
  color: #64748b;
}

.thread-send-btn {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  border: none;
  background: #a78bfa;
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s;
}

.thread-send-btn:hover:not(:disabled) {
  background: #8b5cf6;
}

.thread-send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
