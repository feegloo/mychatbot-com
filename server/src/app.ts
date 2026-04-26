import cors from "cors"
import express, { type Express, type Request, type Response } from "express"
import type { PubSub } from "@google-cloud/pubsub"
import type { Pool } from "pg"
import type { AskRequestBody, PendingAskRegistry, ServerConfig, SseClientRegistry } from "./types.js"
import { handleAsk } from "./ask.js"
import { SERVICE_NAME } from "./const.js"
import { insertConversationMetadata } from "./db.js"
import {
    createConnectedPayload,
    createHeartbeatPayload,
    registerSseClient,
    unregisterSseClient,
    writeSseHeaders,
    writeSseMessage
} from "./sse.js"
import { captureDebugMessage } from "./sentry.js"
import { getFingerprint, getTraceId } from "./utils.js"

/**
 * Creates and wires Express app.
 */
export function createApp(
    config: ServerConfig,
    pubsub: PubSub,
    pool: Pool | null,
    sseRegistry: SseClientRegistry,
    pending: PendingAskRegistry
): Express {
    const app = express()

    app.use(cors({ origin: createCorsOriginChecker(config) }))
    app.use(express.json({ limit: "2mb" }))
    app.use(express.static(config.frontendDistPath))

    app.get("/health", handleHealth)
    app.get("/api/events/:uid", (req, res) => handleEventSource(req, res, pool, sseRegistry))
    app.post("/ask", (req: Request<Record<string, string>, unknown, AskRequestBody>, res) => handleAsk(req, res, config, pubsub, pool, pending))
    app.all("/api/*", (req, res) => handleApiWildcard(req, res, pool))
    app.get(["/", "/c/*", "/m/*"], (_req, res) => res.sendFile("index.html", { root: config.frontendDistPath }))

    return app
}

/**
 * Responds to Cloud Run health checks.
 */
function handleHealth(_req: Request, res: Response): void {
    res.json({ ok: true, service: SERVICE_NAME })
}

/**
 * Creates CORS origin callback for old domain, local dev, and GCP-generated URLs.
 */
function createCorsOriginChecker(config: ServerConfig) {
    return (origin: string | undefined, callback: (error: Error | null, allow?: boolean) => void): void => {
        if (!origin || config.allowedOrigins.includes(origin) || origin === config.publicAppDomain) {
            callback(null, true)
            return
        }

        if (origin.endsWith(".run.app") || origin.endsWith(".cloudfunctions.net")) {
            callback(null, true)
            return
        }

        callback(null, false)
    }
}

/**
 * Handles placeholder /api/* endpoints.
 */
async function handleApiWildcard(req: Request, res: Response, pool: Pool | null): Promise<void> {
    const traceId = getTraceId(req)
    const fingerprint = getFingerprint(req)

    await insertConversationMetadata(pool, {
        uid: "home",
        traceId,
        fingerprint,
        source: "server",
        eventType: "api_wildcard",
        direction: "in",
        payload: { method: req.method, path: req.path },
        message: "server handled /api wildcard request"
    })

    if (req.method === "GET") {
        res.json({ ok: true, message: "hello-world", traceId })
        return
    }

    if (req.method === "POST") {
        res.status(202).json({ ok: true, status: "accepted", traceId })
        return
    }

    res.status(405).json({ ok: false, error: "method-not-allowed", traceId })
}

/**
 * Opens EventSource stream and records connection metadata.
 */
async function handleEventSource(req: Request, res: Response, pool: Pool | null, registry: SseClientRegistry): Promise<void> {
    const uid = req.params.uid
    const traceId = getTraceId(req)
    const fingerprint = getFingerprint(req)

    writeSseHeaders(res)
    registerSseClient(registry, fingerprint, res)
    writeSseMessage(res, "connected", createConnectedPayload({ uid, traceId, fingerprint }))

    await insertConversationMetadata(pool, {
        uid,
        traceId,
        fingerprint,
        source: "server",
        eventType: "sse_connected",
        direction: "in",
        payload: { uid },
        message: "browser opened SSE stream"
    })

    captureDebugMessage("server EventSource connected", { uid, traceId, fingerprint })

    const timer = setInterval(() => {
        writeSseMessage(res, "heartbeat", createHeartbeatPayload({ uid, traceId, fingerprint }))
    }, 10_000)

    req.on("close", () => {
        clearInterval(timer)
        unregisterSseClient(registry, fingerprint, res)
        captureDebugMessage("server EventSource closed", { uid, traceId, fingerprint })
    })
}
