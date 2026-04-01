<template>
  <div class="header" style="margin-bottom: 12px">
    <div style="flex: 1; min-width: 0;">
        <div style="height: 40px;">
      <h1
        v-if="!editingName"
        class="conv-title"
        :title="canUpload ? 'Click to rename' : ''"
        :style="canUpload ? 'cursor: pointer' : ''"
        @click="canUpload && startRename()"
      >{{ conversationTitle }}</h1>
      <input
        v-else
        ref="nameInput"
        class="conv-title-input"
        v-model="editNameValue"
        @keydown.enter="saveRename"
        @keydown.escape="editingName = false"
        @blur="saveRename"
      />
      </div>
      <div style="display: flex; gap: 8px">
        <div class="status-badge">status: {{ status.status }}</div>
        <div class="status-badge">role: {{ status.role }}</div>
      </div>
    </div>
    <div style="display:flex; gap:12px">
      <button class="button secondary" @click="copyUrl">Share</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from "vue";
import { renameConversation, type ConversationStatus } from "../api";

const props = defineProps<{
  status: ConversationStatus;
  conversationId: string;
  conversationTitle: string;
  canUpload: boolean;
}>();

const emit = defineEmits<{
  renamed: [name: string];
}>();

const editingName = ref(false);
const editNameValue = ref("");
const nameInput = ref<HTMLInputElement | null>(null);

async function startRename() {
  editingName.value = true;
  editNameValue.value = props.status.displayName || props.conversationTitle;
  await nextTick();
  nameInput.value?.select();
}

async function saveRename() {
  if (!editingName.value) return;
  editingName.value = false;
  const trimmed = editNameValue.value.trim();
  if (!trimmed || trimmed === props.status.displayName) return;
  await renameConversation(props.conversationId, trimmed);
  emit("renamed", trimmed);
}

async function copyUrl() {
  await navigator.clipboard.writeText(window.location.href);
}
</script>
