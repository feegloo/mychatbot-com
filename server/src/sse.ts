import type { Response } from "express"
import type { SseClientRegistry, SseParams, WorkerAnswerPayload } from "./types.js"
import { nowIso } from "./utils.js"

/**
 * Creates SSE registry grouped by browser fingerprint.
 */
export function createSseRegistry(): SseClientRegistry {
    return new Map()
}

/**
 * Writes headers required by browser EventSource.
 */
export function writeSseHeaders(res: Response): void {
    res.setHeader("Content-Type", "text/event-stream")
    res.setHeader("Cache-Control", "no-cache, no-transform")
    res.setHeader("Connection", "keep-alive")
    res.flushHeaders?.()
}

/**
 * Registers response stream under a browser fingerprint.
 */
export function registerSseClient(registry: SseClientRegistry, fingerprint: string, res: Response): void {
    const clients = registry.get(fingerprint) || new Set<Response>()
    clients.add(res)
    registry.set(fingerprint, clients)
}

/**
 * Removes closed response stream from the registry.
 */
export function unregisterSseClient(registry: SseClientRegistry, fingerprint: string, res: Response): void {
    const clients = registry.get(fingerprint)

    if (!clients) {
        return
    }

    clients.delete(res)

    if (clients.size === 0) {
        registry.delete(fingerprint)
    }
}

/**
 * Writes one named SSE event.
 */
export function writeSseMessage(res: Response, event: string, payload: unknown): void {
    res.write(`event: ${event}\n`)
    res.write(`data: ${JSON.stringify(payload)}\n\n`)
}

/**
 * Broadcasts worker answer to open SSE clients for matching fingerprint.
 */
export function broadcastAnswer(registry: SseClientRegistry, payload: WorkerAnswerPayload): void {
    const clients = registry.get(payload.fingerprint)

    if (!clients) {
        return
    }

    for (const client of clients) {
        writeSseMessage(client, "answer", payload)
    }
}

/**
 * Creates connected event payload.
 */
export function createConnectedPayload(params: SseParams): Record<string, string> {
    return {
        type: "connected",
        uid: params.uid,
        traceId: params.traceId,
        fingerprint: params.fingerprint,
        timestamp: nowIso()
    }
}

/**
 * Creates heartbeat event payload.
 */
export function createHeartbeatPayload(params: SseParams): Record<string, string> {
    return {
        type: "heartbeat",
        uid: params.uid,
        traceId: params.traceId,
        fingerprint: params.fingerprint,
        timestamp: nowIso()
    }
}
