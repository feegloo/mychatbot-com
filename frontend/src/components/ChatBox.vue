<script setup lang="ts">
import { ref } from "vue"
import type { ChatMessage } from "../types"
import MessagesList from "./MessagesList.vue"

const props = defineProps<{
    messages: ChatMessage[]
    loading: boolean
}>()

const emit = defineEmits<{
    ask: [question: string]
}>()

const input = ref("")

/**
 * Sends input value to parent and clears the field.
 */
function handleSubmit(): void {
    const value = input.value.trim()

    if (!value) {
        return
    }

    emit("ask", value)
    input.value = ""
}
</script>

<template>
    <section class="card">
        <h2>Ask worker</h2>
        <MessagesList :messages="props.messages" />
        <form class="chat-form" @submit.prevent="handleSubmit">
            <input v-model="input" type="text" placeholder="Write message and press Enter..." autocomplete="off" />
            <button type="submit" :disabled="props.loading">Ask</button>
        </form>
    </section>
</template>
