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

    <button v-if="showDonate" class="conv-nav-donate" @click="handleDonate">Donate $</button>
  </nav>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from "vue";
import { useRoute } from "vue-router";
import { loadStripe, type Stripe, type PaymentRequest } from "@stripe/stripe-js";
import { listMyConversations, type ConversationSummary } from "../api";
import { cleanFileName } from "../utils/text";
import axios from "axios";

const api = axios.create({
  // @ts-ignore
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:3000/api",
});

defineEmits<{ navigate: [] }>();

const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !(window as any).MSStream;
const showDonate = ref(false);

let stripeInstance: Stripe | null = null;
let paymentRequest: PaymentRequest | null = null;

async function initStripe() {
  if (!isIOS) return;
  // @ts-ignore
  const key = import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY;
  if (!key) return;

  stripeInstance = await loadStripe(key);
  if (!stripeInstance) return;

  paymentRequest = stripeInstance.paymentRequest({
    country: "US",
    currency: "usd",
    total: { label: "ChatRAG Donation", amount: 100 },
    requestPayerName: false,
    requestPayerEmail: false,
  });

  const result = await paymentRequest.canMakePayment();
  if (result?.applePay) {
    showDonate.value = true;

    paymentRequest.on("paymentmethod", async (ev) => {
      try {
        const { data } = await api.post("/donate");
        const { error } = await stripeInstance!.confirmCardPayment(
          data.clientSecret,
          { payment_method: ev.paymentMethod.id },
          { handleActions: false }
        );
        if (error) {
          ev.complete("fail");
        } else {
          ev.complete("success");
        }
      } catch {
        ev.complete("fail");
      }
    });
  }
}

async function handleDonate() {
  if (!paymentRequest) return;
  paymentRequest.show();
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
  initStripe();
  window.addEventListener('conversation-updated', load);
});

onUnmounted(() => {
  stopPolling();
  window.removeEventListener('conversation-updated', load);
});

onMounted(load);
</script>
