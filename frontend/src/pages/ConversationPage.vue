<template>
  <div class="page">
    <ConversationHeader
      :status="status"
      :conversationId="conversationId"
      :conversationTitle="conversationTitle"
      :canUpload="canUpload"
      @renamed="status.displayName = $event"
    />

    <p v-if="status.errorMessage" style="color:#f87171; margin-bottom:16px">
      {{ status.errorMessage }}
    </p>

    <div class="grid grid-2">
      <section class="chat-panel">

        <p v-if="loaded && status.status !== 'ready'" style="margin-bottom:12px; color:#fbbf24">
          Conversation is {{ status.status }} uploaded files. 
          <br/> Asking will work after indexing finishes successfully.
        </p>

        <div class="chat-log" ref="chatContainer" style="flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; padding-right: 8px">
          <div style="flex: 1"></div>
          <ChatMessageItem
            v-for="(msg, index) in messages"
            :key="msg.id || index"
            :msg="msg"
            :asking="asking"
            :activeCitationIndex="activeCitationTab[index] ?? 0"
            @update:activeCitationIndex="activeCitationTab[index] = $event"
          />
        </div>

        <div class="chat-input-bar">
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

      <ConversationSidebar
        ref="sidebarRef"
        :status="status"
        :conversationId="conversationId"
        :canUpload="canUpload"
        @reload="onReload"
        @select-question="question = $event; submitQuestion()"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch, nextTick } from "vue";
import {
  askQuestion,
  getConversation,
  type ConversationStatus,
  type ChatMessage,
} from "../api";
import { cleanFileName } from "../utils/text";
import ConversationHeader from "../components/ConversationHeader.vue";
import ChatMessageItem from "../components/ChatMessage.vue";
import ConversationSidebar from "../components/ConversationSidebar.vue";

const props = defineProps<{ conversationId: string }>();

const conversationId = props.conversationId;
const question = ref("");
const asking = ref(false);
const questionInput = ref<HTMLTextAreaElement | null>(null);
const chatContainer = ref<HTMLDivElement | null>(null);
const sidebarRef = ref<InstanceType<typeof ConversationSidebar> | null>(null);
const loaded = ref(false);

const status = ref<ConversationStatus>({
  conversationId,
  displayName: null,
  status: "processing",
  role: "viewer",
  files: [],
  messages: [],
  suggestedQuestions: [],
  accessRequests: []
});
const messages = ref<ChatMessage[]>([]);
const activeCitationTab = ref<Record<number, number>>({});

const canUpload = computed(() => status.value.role === "owner" || status.value.role === "editor");

const conversationTitle = computed(() => {
  if (status.value.displayName) return status.value.displayName;
  if (status.value.files.length) {
    return status.value.files.map(f => cleanFileName(f.originalName)).join(", ");
  }
  return `Conversation ${conversationId.slice(0, 8)}…`;
});

watch(conversationTitle, (title) => {
  document.title = `chatbotqa.app | ${title}`;
}, { immediate: true });

async function loadConversation() {
  const response = await getConversation(conversationId);
  status.value = response;
  if (!asking.value) {
    messages.value = response.messages || [];
  }
  loaded.value = true;
}

async function onReload() {
  await loadConversation();
  window.dispatchEvent(new CustomEvent('conversation-updated'));
}

function scrollToBottom() {
  if (chatContainer.value) {
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

  const assistantPlaceholder: ChatMessage = { role: "assistant", content: "" };
  messages.value.push(assistantPlaceholder);

  try {
    const response = await askQuestion(conversationId, currentQuestion);
    assistantPlaceholder.content = response.answer;
    assistantPlaceholder.citations = response.citations;
    await loadConversation();
  } finally {
    asking.value = false;
  }
}

function submitQuestion() {
  if (asking.value || !question.value.trim()) return;
  ask();
  if (questionInput.value) {
    questionInput.value.style.height = 'auto';
  }
}

function autoResize(e: Event) {
  const el = e.target as HTMLTextAreaElement;
  el.style.height = 'auto';
  el.style.height = el.scrollHeight + 'px';
}

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
  loaded.value = true;
  await nextTick();
  setTimeout(() => scrollToBottom(), 100);

  intervalHandle = window.setInterval(async () => {
    await loadConversation();
    sidebarRef.value?.pollAccessRequest();
  }, 1000);
});

onUnmounted(() => {
  if (intervalHandle !== undefined) {
    clearInterval(intervalHandle);
  }
});
</script>
