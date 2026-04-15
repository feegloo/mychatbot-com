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
          :msg="{ id: message.id, role: message.role, content: message.content, citations: message.citations }"
          :asking="false"
          :conversationId="message.conversationId"
        />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { getSharedMessage, type SharedMessage } from "../api";
import ChatMessageItem from "../components/ChatMessage.vue";

const props = defineProps<{ messageId: string }>();

const message = ref<SharedMessage | null>(null);
const loading = ref(true);
const error = ref("");

async function load() {
  loading.value = true;
  error.value = "";
  try {
    message.value = await getSharedMessage(props.messageId);
    document.title = `${message.value.displayName || "Shared answer"} | chatrag.app`;
  } catch {
    error.value = "Message not found";
  } finally {
    loading.value = false;
  }
}

onMounted(load);
watch(() => props.messageId, load);
</script>

<style scoped>
.shared-message-page {
  max-width: 800px;
  justify-content: flex-start;
  gap: 16px;
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
</style>
