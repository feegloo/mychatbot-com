<template>
  <nav class="conv-nav">
    <router-link to="/" class="conv-nav-new button">
      + New conversation
    </router-link>

    <div class="conv-nav-list">
      <router-link
        v-for="conv in conversations"
        :key="conv.conversationId"
        :to="`/c/${conv.conversationId}`"
        class="conv-nav-item"
        :class="{ active: conv.conversationId === currentId }"
      >
        <span class="conv-nav-name">{{ convLabel(conv) }}</span>
        <span class="conv-nav-badge" :class="conv.status">{{ conv.status }}</span>
      </router-link>

      <p v-if="!conversations.length && !loading" class="conv-nav-empty">
        No conversations yet
      </p>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from "vue";
import { useRoute } from "vue-router";
import { listMyConversations, type ConversationSummary } from "../api";
import { cleanFileName } from "../utils/text";

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

async function load() {
  loading.value = true;
  try {
    conversations.value = await listMyConversations();
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

onMounted(load);
</script>
