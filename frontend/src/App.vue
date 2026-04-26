<script setup lang="ts">
import { onMounted } from "vue"
import UploadBox from "./components/UploadBox.vue"
import ChatBox from "./components/ChatBox.vue"
import EventLog from "./components/EventLog.vue"
import { createRuntimeConfig } from "./lib/config"
import { getOrCreateFingerprint } from "./lib/fingerprint"
import { initSentry } from "./lib/sentry"
import { useChat } from "./composables/useChat"
import { useSse } from "./composables/useSse"
import { useUpload } from "./composables/useUpload"

const config = createRuntimeConfig()
const fingerprint = getOrCreateFingerprint()
const { messages, loading, ask } = useChat(fingerprint)
const { events, open } = useSse(fingerprint)
const { status, activeConversationId, upload } = useUpload(config, fingerprint)

initSentry(config)

/**
 * Opens SSE connection as soon as the home page loads.
 */
onMounted(() => {
    open(activeConversationId.value)
})
</script>

<template>
    <main>
        <h1>ChatRAG</h1>
        <p>
            Option A: frontend can call generated GCP URLs now, and later the new project can replace the old
            deployment behind chatrag.app.
        </p>
        <p><strong>Fingerprint:</strong> {{ fingerprint }}</p>

        <UploadBox :status="status" @upload="upload" />
        <ChatBox :messages="messages" :loading="loading" @ask="ask" />
        <EventLog :events="events" />
    </main>
</template>

<style>
body {
    margin: 0;
    font-family: system-ui, sans-serif;
    background: #fafafa;
    color: #111;
}

main {
    max-width: 900px;
    margin: 40px auto;
    padding: 0 20px 60px;
}

button,
input {
    font: inherit;
}

.card {
    margin: 18px 0;
    padding: 18px;
    border: 1px solid #ddd;
    border-radius: 14px;
    background: white;
}

form {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
}

.chat-form input {
    flex: 1;
    min-width: 240px;
    padding: 8px 10px;
}

.messages {
    display: grid;
    gap: 8px;
    margin-bottom: 14px;
}

.message {
    display: grid;
    gap: 4px;
    padding: 10px 12px;
    border: 1px solid #ddd;
    border-radius: 10px;
}

.message.user {
    background: #f6f6f6;
}

pre {
    min-height: 160px;
    padding: 12px;
    border: 1px solid #ddd;
    border-radius: 10px;
    white-space: pre-wrap;
    background: #fcfcfc;
}
</style>
