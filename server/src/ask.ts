import type { PubSub } from "@google-cloud/pubsub"
import type { Request, Response } from "express"
import type { Pool } from "pg"
import type {
    AskRequestBody,
    AskTimeoutError,
    PendingAskRegistry,
    ServerConfig,
    WorkerAnswerPayload
} from "./types.js"
import { insertConversationMetadata } from "./db.js"
import { publishAskMessage } from "./pubsub.js"
import { captureDebugMessage, captureException } from "./sentry.js"
import { getFingerprint, getQuestion, getTraceId } from "./utils.js"

/**
 * Creates in-memory registry for pending /ask HTTP responses.
 */
export function createPendingAskRegistry(): PendingAskRegistry {
    return new Map()
}

/**
 * Handles plain HTTP /ask with 20-second wait for answer Pub/Sub message.
 */
export async function handleAsk(
    req: Request<Record<string, string>, unknown, AskRequestBody>,
    res: Response,
    config: ServerConfig,
    pubsub: PubSub,
    pool: Pool | null,
    pending: PendingAskRegistry
): Promise<void> {
    const traceId = getTraceId(req)
    const fingerprint = getFingerprint(req)
    const question = getQuestion(req)
    const uid = req.body?.uid || "home"

    if (!question) {
        res.status(400).json({ ok: false, error: "missing-question", traceId })
        return
    }

    try {
        const waitPromise = waitForAnswer(traceId, config.askTimeoutMs, pending)

        await insertConversationMetadata(pool, {
            uid,
            traceId,
            fingerprint,
            source: "server",
            eventType: "ask_received",
            direction: "in",
            payload: { question },
            message: "user sent /ask request to server"
        })

        await publishAskMessage(pubsub, config, {
            type: "ask",
            uid,
            traceId,
            fingerprint,
            value: JSON.stringify({ question })
        })

        await insertConversationMetadata(pool, {
            uid,
            traceId,
            fingerprint,
            source: "server",
            eventType: "pubsub_worker_topic_published",
            topicName: config.workerTopic,
            direction: "out",
            payload: { type: "ask", question },
            message: "server published ask message to worker topic"
        })

        const answer = await waitPromise

        await insertConversationMetadata(pool, {
            uid,
            traceId,
            fingerprint,
            source: "server",
            eventType: "ask_response_returned",
            direction: "out",
            payload: answer,
            message: "server returned worker answer to HTTP user"
        })

        captureDebugMessage("server /ask answered", { traceId, fingerprint, question, answer })
        res.json({ ok: true, traceId, fingerprint, question, answer: answer.value, answerPayload: answer })
    } catch (error) {
        captureException(error)
        const statusCode = isAskTimeoutError(error) ? 504 : 502
        const message = error instanceof Error ? error.message : "unknown-error"

        res.status(statusCode).json({ ok: false, error: message, traceId, fingerprint })
    }
}

/**
 * Waits until answer subscriber resolves matching trace id.
 */
export function waitForAnswer(traceId: string, timeoutMs: number, pending: PendingAskRegistry): Promise<WorkerAnswerPayload> {
    return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
            pending.delete(traceId)
            reject(createAskTimeoutError(traceId))
        }, timeoutMs)

        pending.set(traceId, { resolve, reject, timeout })
    })
}

/**
 * Resolves pending /ask request for matching trace id.
 */
export function resolvePendingAnswer(pending: PendingAskRegistry, payload: WorkerAnswerPayload): boolean {
    const entry = pending.get(payload.traceId)

    if (!entry) {
        return false
    }

    clearTimeout(entry.timeout)
    pending.delete(payload.traceId)
    entry.resolve(payload)
    return true
}

/**
 * Creates typed timeout error.
 */
function createAskTimeoutError(traceId: string): AskTimeoutError {
    const error = new Error(`Timeout waiting for worker answer traceId=${traceId}`) as AskTimeoutError
    error.code = "ASK_TIMEOUT"
    return error
}

/**
 * Checks whether an error is ask timeout.
 */
function isAskTimeoutError(error: unknown): error is AskTimeoutError {
    return error instanceof Error && (error as AskTimeoutError).code === "ASK_TIMEOUT"
}
