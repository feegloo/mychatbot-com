<template>
  <div class="header" style="margin-bottom: 12px">
    <div style="flex: 1; min-width: 0; max-width: 60%;">
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
      <button class="button secondary" style="width: 180px; padding: 8px 10px" @click="copyUrl">
        <template v-if="copied">Link copied!</template>
        <template v-else><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: -2px; margin-right: 4px"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>Share conversation</template>
      </button>
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
const copied = ref(false);

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
  copied.value = true;
  setTimeout(() => { copied.value = false; }, 2000);
}
</script>
