import { ref } from "vue"
import type { RuntimeConfig, UploadResponse } from "../types"
import { createTraceId } from "../lib/fingerprint"
import { captureFrontendDebug } from "../lib/sentry"

/**
 * Creates upload state and Cloud Function upload action.
 */
export function useUpload(config: RuntimeConfig, fingerprint: string) {
    const status = ref("Ready")
    const activeConversationId = ref("home")

    async function upload(file: File): Promise<void> {
        const traceId = createTraceId()
        const body = new FormData()
        body.append("file", file)
        body.append("traceId", traceId)
        body.append("fingerprint", fingerprint)

        status.value = `Uploading ${file.name}...`
        captureFrontendDebug("frontend upload started", { traceId, fingerprint, fileName: file.name })

        const response = await fetch(config.uploadUrl, {
            method: "POST",
            headers: {
                "x-trace-id": traceId,
                fingerprint
            },
            body
        })

        const payload = await response.json() as UploadResponse

        if (!response.ok || !payload.ok) {
            throw new Error(`Upload failed: ${JSON.stringify(payload)}`)
        }

        activeConversationId.value = payload.uid
        status.value = `Uploaded. Conversation: ${payload.uid}`
        window.history.pushState({}, "", `/c/${payload.uid}`)
    }

    return {
        status,
        activeConversationId,
        upload
    }
}
