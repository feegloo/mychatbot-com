<template>
  <nav class="conv-nav">
    <router-link to="/" class="conv-nav-new button" @click="$emit('navigate')">
      + New chat
    </router-link>

    <div class="conv-nav-list">
      <router-link
        v-for="conv in conversations"
        :key="conv.conversationId"
        :to="`/c/${conv.conversationId}`"
        class="conv-nav-item"
        :class="{ active: conv.conversationId === currentId }"
        @click="$emit('navigate')"
      >
        <span class="conv-nav-name">{{ convLabel(conv) }}</span>
        <span v-if="conv.status === 'processing'" class="conv-nav-dot processing"></span>
        <span v-else-if="conv.status === 'failed'" class="conv-nav-dot failed"></span>
      </router-link>

      <p v-if="!conversations.length && !loading" class="conv-nav-empty">
        No conversations yet
      </p>
    </div>

    <button class="conv-nav-donate" @click="handleDonate">Donate $</button>
  </nav>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from "vue";
import { useRoute } from "vue-router";
import { listMyConversations, type ConversationSummary } from "../api";
import { cleanFileName } from "../utils/text";

defineEmits<{ navigate: [] }>();

async function handleDonate() {
  if (!window.PaymentRequest) {
    alert("Apple Pay is not available on this device.");
    return;
  }

  const methods: PaymentMethodData[] = [
    {
      supportedMethods: "https://apple.com/apple-pay",
      data: {
        version: 3,
        merchantIdentifier: "merchant.app.chatrag",
        merchantCapabilities: ["supports3DS"],
        supportedNetworks: ["visa", "masterCard", "amex"],
        countryCode: "US",
      },
    },
  ];

  const details: PaymentDetailsInit = {
    total: {
      label: "ChatRAG Donation",
      amount: { currency: "USD", value: "1.00" },
    },
  };

  try {
    const request = new PaymentRequest(methods, details);
    const canMake = await request.canMakePayment();
    if (!canMake) {
      alert("Apple Pay is not available on this device.");
      return;
    }
    const response = await request.show();
    await response.complete("success");
  } catch {
    // user cancelled
  }
}

function convLabel(conv: ConversationSummary): string {
  if (conv.displayName) return conv.displayName;
  if (conv.fileNames?.length) {
    return conv.fileNames.map(cleanFileName).join(", ");
  }
  return `Conversation ${conv.conversationId.slice(0, 8)}…`;
}

const route = useRoute();
const conversations = ref<ConversationSummary[]>([]);
const loading = ref(false);
const currentId = ref("");
let pollHandle: number | undefined;

function hasProcessing() {
  return conversations.value.some(c => c.status === "processing");
}

function startPolling() {
  stopPolling();
  pollHandle = window.setInterval(async () => {
    await load();
    if (!hasProcessing()) stopPolling();
  }, 1500);
}

function stopPolling() {
  if (pollHandle !== undefined) {
    clearInterval(pollHandle);
    pollHandle = undefined;
  }
}

async function load() {
  loading.value = true;
  try {
    conversations.value = await listMyConversations();
    if (hasProcessing() && pollHandle === undefined) {
      startPolling();
    }
  } catch {
    // silently fail – sidebar is non-critical
  } finally {
    loading.value = false;
  }
}

watch(
  () => route.params.conversationId,
  (id) => {
    currentId.value = (id as string) || "";
  },
  { immediate: true }
);

// Reload list when navigating to a new conversation (e.g. after upload)
watch(
  () => route.path,
  () => load()
);

onMounted(() => {
  load();
  window.addEventListener('conversation-updated', load);
});

onUnmounted(() => {
  stopPolling();
  window.removeEventListener('conversation-updated', load);
});

onMounted(load);
</script>
