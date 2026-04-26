import type { Response } from "express"

export type ServerConfig = {
    port: number
    frontendDistPath: string
    workerTopic: string
    answerSubscription: string
    askTimeoutMs: number
    databaseUrl?: string
    sentryDsn?: string
    sentryEnvironment: string
    sentryRelease: string
    allowedOrigins: string[]
    publicAppDomain: string
}

export type AskRequestBody = {
    question?: string
    uid?: string
    fingerprint?: string
    traceId?: string
}

export type AskTopicMessage = {
    type: "ask"
    uid: string
    traceId: string
    fingerprint: string
    value: string
}

export type WorkerAnswerPayload = {
    type?: string
    uid?: string
    traceId: string
    fingerprint: string
    value?: string
    answer?: string
    timestamp?: string
    [key: string]: unknown
}

export type PendingAskRequest = {
    resolve: (payload: WorkerAnswerPayload) => void
    reject: (error: AskTimeoutError) => void
    timeout: NodeJS.Timeout
}

export type AskTimeoutError = Error & {
    code?: "ASK_TIMEOUT"
}

export type SseParams = {
    uid: string
    traceId: string
    fingerprint: string
}

export type MetadataEventInput = {
    uid: string
    traceId: string
    fingerprint?: string
    source: string
    eventType: string
    topicName?: string
    direction?: string
    payload?: unknown
    message: string
}

export type SseClientRegistry = Map<string, Set<Response>>
export type PendingAskRegistry = Map<string, PendingAskRequest>
