import { ref } from "vue"
import type { AskResponse, ChatMessage } from "../types"
import { createTraceId } from "../lib/fingerprint"
import { captureFrontendDebug } from "../lib/sentry"

/**
 * Creates chat state and /ask HTTP action for Vue components.
 */
export function useChat(fingerprint: string) {
    const messages = ref<ChatMessage[]>([])
    const loading = ref(false)

    async function ask(question: string): Promise<void> {
        const traceId = createTraceId()
        const cleanQuestion = question.trim()

        if (!cleanQuestion) {
            return
        }

        messages.value.push(createMessage("user", cleanQuestion))
        loading.value = true
        captureFrontendDebug("frontend user submitted ask", { traceId, fingerprint, question: cleanQuestion })

        try {
            const response = await fetch("/ask", {
                method: "POST",
                headers: {
                    "content-type": "application/json",
                    "x-trace-id": traceId,
                    fingerprint
                },
                body: JSON.stringify({ question: cleanQuestion, fingerprint, traceId, uid: "home" })
            })

            const payload = await response.json() as AskResponse
            messages.value.push(createMessage("assistant", payload.answer || payload.error || "No answer"))
        } catch (error) {
            const text = error instanceof Error ? error.message : "Unknown error"
            messages.value.push(createMessage("system", text))
        } finally {
            loading.value = false
        }
    }

    return {
        messages,
        loading,
        ask
    }
}

/**
 * Creates one UI chat message with a stable browser id.
 */
function createMessage(role: ChatMessage["role"], text: string): ChatMessage {
    return {
        id: crypto.randomUUID(),
        role,
        text
    }
}
