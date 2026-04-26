export type ChatMessage = {
    id: string
    role: "user" | "assistant" | "system"
    text: string
}

export type RuntimeConfig = {
    appBaseUrl: string
    uploadUrl: string
    sentryDsn: string
    sentryEnvironment: string
}

export type AskResponse = {
    ok: boolean
    traceId: string
    fingerprint: string
    question?: string
    answer?: string
    error?: string
}

export type UploadResponse = {
    ok: boolean
    uid: string
    traceId: string
    url?: string
}
