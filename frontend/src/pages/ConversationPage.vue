<template>
  <div class="page">
    <div class="header">
      <div>
        <h1>Conversation {{ conversationId }}</h1>
        <div class="status-badge">Status: {{ status.status }}</div>
        <p v-if="status.status === 'failed' && status.errorMessage" style="color:#b91c1c; margin-top:10px;">
  {{ status.errorMessage }}
</p>
      </div>
      <div>
        <button class="button secondary" @click="copyUrl">Copy shareable URL</button>
      </div>
    </div>

    <div class="grid grid-2">
      <section class="card">
        <h2>Chat</h2>

        <div style="margin-bottom: 12px">
          <textarea
            class="big-input"
            v-model="question"
            placeholder="Ask a question about the uploaded documents..."
          />
        </div>

        <div style="display:flex; gap:12px; margin-bottom:12px;">
          <button class="button" :disabled="asking || status.status !== 'ready'" @click="ask">
            {{ asking ? "Thinking..." : "Ask question" }}
          </button>
          <button class="button secondary" :disabled="asking || status.status !== 'ready'" @click="askStreaming">
            Live answer
          </button>
        </div>

        <div class="chat-log">
          <div v-for="(msg, index) in messages" :key="index" class="message" :class="msg.role">
            <strong>{{ msg.role === 'user' ? 'You' : 'Assistant' }}</strong>
            <p style="white-space: pre-wrap">{{ msg.content }}</p>

            <div v-if="msg.citations?.length" class="sources">
              <div v-for="citation in msg.citations" :key="citation.chunkId" class="source-card">
                <strong>{{ citation.fileName }}</strong>
                <div v-if="citation.section">Section: {{ citation.section }}</div>
                <div v-if="citation.page !== null && citation.page !== undefined">Page: {{ citation.page }}</div>
                <div style="margin-top:8px; white-space: pre-wrap">{{ citation.text }}</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <aside class="card">
        <h2>Uploaded files</h2>
        <div>
          <span v-for="file in status.files" :key="file.id" class="file-pill">
            {{ file.originalName }}
          </span>
        </div>

        <h2 style="margin-top:24px">Suggested questions</h2>
        <div>
          <button
            v-for="q in status.suggestedQuestions"
            :key="q"
            class="question-pill"
            style="border:none; cursor:pointer"
            @click="question = q"
          >
            {{ q }}
          </button>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { askQuestion, getConversation, getStreamUrl, type ConversationStatus } from "../api";

type Citation = {
  fileName: string;
  chunkId: string;
  text: string;
  section?: string;
  page?: number | null;
};

type Message = {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
};

const props = defineProps<{ conversationId: string }>();

const conversationId = props.conversationId;
const question = ref("");
const asking = ref(false);
const status = ref<ConversationStatus>({
  conversationId,
  status: "processing",
  files: [],
  suggestedQuestions: []
});
const messages = ref<Message[]>([]);

async function loadConversation() {
  status.value = await getConversation(conversationId);
}

async function ask() {
  if (!question.value.trim()) return;
  asking.value = true;

  messages.value.push({ role: "user", content: question.value });

  try {
    const response = await askQuestion(conversationId, question.value);
    messages.value.push({
      role: "assistant",
      content: response.answer,
      citations: response.citations
    });
    question.value = "";
  } finally {
    asking.value = false;
  }
}

async function askStreaming() {
  if (!question.value.trim()) return;
  asking.value = true;

  const currentQuestion = question.value;
  messages.value.push({ role: "user", content: currentQuestion });

  const assistantMessage: Message = {
    role: "assistant",
    content: "",
    citations: []
  };
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

  source.addEventListener("done", () => {
    source.close();
    asking.value = false;
    question.value = "";
  });

  source.addEventListener("error", () => {
    source.close();
    asking.value = false;
  });
}

async function copyUrl() {
  await navigator.clipboard.writeText(window.location.href);
}

onMounted(async () => {
  await loadConversation();
  if (status.value.status === "processing") {
    const interval = setInterval(async () => {
      await loadConversation();
      if (status.value.status !== "processing") {
        clearInterval(interval);
      }
    }, 2500);
  }
});
</script>
