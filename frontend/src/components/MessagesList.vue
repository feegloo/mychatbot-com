<script setup lang="ts">
import type { ChatMessage } from "../types"

const props = defineProps<{
    messages: ChatMessage[]
}>()
</script>

<template>
    <div class="messages">
        <article v-for="message in props.messages" :key="message.id" :class="['message', message.role]">
            <strong>{{ message.role }}</strong>
            <span>{{ message.text }}</span>
        </article>
    </div>
</template>
