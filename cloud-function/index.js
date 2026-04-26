import { PubSub } from "@google-cloud/pubsub"
import { randomUUID } from "node:crypto"
import { Storage } from "@google-cloud/storage"
import Busboy from "busboy"
import pg from "pg"
import * as Sentry from "@sentry/node"
import { nodeProfilingIntegration } from "@sentry/profiling-node"

const { Pool } = pg
const config = createConfig()
const pubsub = new PubSub()
const storage = new Storage()
const pool = createDatabasePool(config)

initSentry()

/**
 * Reads Cloud Function configuration from environment variables.
 */
function createConfig() {
    return {
        bucket: process.env.GCS_BUCKET,
        topic: process.env.PUBSUB_TOPIC || "chatrag-worker-topic",
        databaseUrl: process.env.DATABASE_URL,
        sentryDsn: process.env.SENTRY_DSN,
        sentryEnvironment: process.env.SENTRY_ENVIRONMENT || "production",
        sentryRelease: process.env.SENTRY_RELEASE || "chatrag@local",
        allowedOrigins: parseAllowedOrigins(process.env.ALLOWED_ORIGINS),
        publicAppDomain: process.env.PUBLIC_APP_DOMAIN || "https://chatrag.app",
        serverHealthUrl: process.env.SERVER_HEALTH_URL || "",
        prewarmServerTimeoutMs: Number(process.env.PREWARM_SERVER_TIMEOUT_MS || "8000")
    }
}

/**
 * Converts comma-separated CORS origins into array.
 */
function parseAllowedOrigins(value) {
    return String(value || "")
        .split(",")
        .map((origin) => origin.trim())
        .filter(Boolean)
}

/**
 * Creates PostgreSQL connection pool for Cloud Function execution.
 */
function createDatabasePool(runtimeConfig) {
    if (!runtimeConfig.databaseUrl) {
        return null
    }

    return new Pool({
        connectionString: runtimeConfig.databaseUrl,
        max: 2,
        idleTimeoutMillis: 30_000
    })
}

/**
 * Initializes Sentry for upload Cloud Function.
 */
function initSentry() {
    if (!config.sentryDsn) {
        return
    }

    Sentry.init({
        dsn: config.sentryDsn,
        environment: config.sentryEnvironment,
        release: config.sentryRelease,
        integrations: [nodeProfilingIntegration()],
        tracesSampleRate: 1.0,
        profilesSampleRate: 1.0,
        debug: true
    })
}

/**
 * Main HTTP entry point for Cloud Function upload.
 */
export async function uploadHandler(req, res) {
    setCorsHeaders(req, res)

    if (req.method === "OPTIONS") {
        res.status(204).send("")
        return
    }

    if (req.method !== "POST") {
        res.status(405).json({ ok: false, error: "method-not-allowed" })
        return
    }

    try {
        const traceId = getTraceId(req)
        const fingerprint = getFingerprint(req)
        const uid = randomUUID()
        const parsed = await parseMultipartRequest(req)
        const fileName = parsed.fileName || "test.pdf"
        const storageUri = await uploadBufferToGcs(uid, fileName, parsed.buffer)

        await insertConversation({ uid, traceId, fingerprint, fileName, storageUri })
        await insertConversationMetadata({
            uid,
            traceId,
            fingerprint,
            source: "cloud-function",
            eventType: "upload_received",
            direction: "in",
            payload: { fileName, storageUri },
            message: "cloud function received upload and stored file"
        })

        const message = {
            type: "process_pdf",
            uid,
            traceId,
            fingerprint,
            fileName,
            storageUri
        }

        await pubsub.topic(config.topic).publishMessage({ json: message })
        await insertConversationMetadata({
            uid,
            traceId,
            fingerprint,
            source: "cloud-function",
            eventType: "pubsub_worker_topic_published",
            topicName: config.topic,
            direction: "out",
            payload: message,
            message: "cloud function published PDF processing message"
        })

        await prewarmServerAfterUpload({ uid, traceId, fingerprint })

        Sentry.captureMessage("cloud function upload completed", {
            level: "debug",
            extra: { uid, traceId, fingerprint, fileName, storageUri }
        })

        res.json({ ok: true, uid, traceId, url: `/c/${uid}` })
    } catch (error) {
        Sentry.captureException(error)
        res.status(500).json({ ok: false, error: error instanceof Error ? error.message : "unknown-error" })
    }
}

/**
 * Wakes the Cloud Run SSE/HTTP server after frontend upload completes.
 *
 * The server is deployed with min-instances=0 to minimize idle cost. Calling
 * GET /health here makes the first browser navigation/SSE connection after
 * upload much less likely to pay the full cold-start cost. Prewarm failures are
 * logged but do not fail the upload flow.
 */
async function prewarmServerAfterUpload({ uid, traceId, fingerprint }) {
    if (!config.serverHealthUrl) {
        await insertConversationMetadata({
            uid,
            traceId,
            fingerprint,
            source: "cloud-function",
            eventType: "server_prewarm_skipped",
            direction: "out",
            payload: { reason: "SERVER_HEALTH_URL is empty" },
            message: "cloud function skipped server prewarm because SERVER_HEALTH_URL is empty"
        })
        return
    }

    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), config.prewarmServerTimeoutMs)

    try {
        const response = await fetch(config.serverHealthUrl, {
            method: "GET",
            headers: {
                "x-trace-id": traceId,
                fingerprint,
                "user-agent": "chatrag-cloud-function-prewarm"
            },
            signal: controller.signal
        })

        await insertConversationMetadata({
            uid,
            traceId,
            fingerprint,
            source: "cloud-function",
            eventType: "server_prewarm_health_checked",
            direction: "out",
            payload: { serverHealthUrl: config.serverHealthUrl, status: response.status },
            message: "cloud function called Cloud Run server GET /health after upload"
        })

        Sentry.captureMessage("cloud function prewarmed server", {
            level: "debug",
            extra: { uid, traceId, fingerprint, serverHealthUrl: config.serverHealthUrl, status: response.status }
        })
    } catch (error) {
        await insertConversationMetadata({
            uid,
            traceId,
            fingerprint,
            source: "cloud-function",
            eventType: "server_prewarm_failed",
            direction: "out",
            payload: { serverHealthUrl: config.serverHealthUrl, error: error instanceof Error ? error.message : String(error) },
            message: "cloud function failed to prewarm Cloud Run server after upload"
        })

        Sentry.captureException(error)
    } finally {
        clearTimeout(timeout)
    }
}

/**
 * Applies CORS headers for Option A generated GCP URLs and future chatrag.app domain.
 */
function setCorsHeaders(req, res) {
    const origin = req.headers.origin
    const allowed = isAllowedOrigin(origin) ? origin : config.publicAppDomain

    res.setHeader("Access-Control-Allow-Origin", allowed || "*")
    res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS")
    res.setHeader("Access-Control-Allow-Headers", "content-type, x-trace-id, fingerprint, sentry-trace, baggage")
}

/**
 * Checks whether request origin should be accepted.
 */
function isAllowedOrigin(origin) {
    if (!origin) {
        return true
    }

    return config.allowedOrigins.includes(origin) ||
        origin === config.publicAppDomain ||
        origin.endsWith(".run.app") ||
        origin.endsWith(".cloudfunctions.net")
}

/**
 * Reads trace id from headers or creates one.
 */
function getTraceId(req) {
    return req.headers["x-trace-id"] || randomUUID()
}

/**
 * Reads fingerprint from headers.
 */
function getFingerprint(req) {
    return req.headers.fingerprint || "anonymous"
}

/**
 * Parses multipart/form-data upload into filename and buffer.
 */
function parseMultipartRequest(req) {
    return new Promise((resolve, reject) => {
        const busboy = Busboy({ headers: req.headers })
        const chunks = []
        let fileName = "test.pdf"

        busboy.on("file", (_fieldName, file, info) => {
            fileName = info.filename || fileName
            file.on("data", (chunk) => chunks.push(chunk))
        })

        busboy.on("field", () => {})
        busboy.on("error", reject)
        busboy.on("finish", () => resolve({ fileName, buffer: Buffer.concat(chunks) }))
        busboy.end(req.rawBody)
    })
}

/**
 * Uploads buffer to Cloud Storage and returns gs:// URI.
 */
async function uploadBufferToGcs(uid, fileName, buffer) {
    if (!config.bucket) {
        throw new Error("GCS_BUCKET is required")
    }

    const objectName = `uploads/${uid}/${fileName}`
    const file = storage.bucket(config.bucket).file(objectName)

    await file.save(buffer.length ? buffer : Buffer.from("hello world pdf placeholder"), {
        contentType: "application/pdf"
    })

    return `gs://${config.bucket}/${objectName}`
}

/**
 * Inserts newly created conversation row.
 */
async function insertConversation({ uid, traceId, fileName, storageUri }) {
    if (!pool) {
        return
    }

    await pool.query(
        `
        INSERT INTO conversations(uid, trace_id, file_name, storage_uri, status)
        VALUES ($1, $2, $3, $4, 'uploaded')
        ON CONFLICT (uid) DO NOTHING
        `,
        [uid, traceId, fileName, storageUri]
    )
}

/**
 * Inserts one debug event into conversations_metadatas.
 */
async function insertConversationMetadata(event) {
    if (!pool) {
        return
    }

    await pool.query(
        `
        INSERT INTO conversations_metadatas(
            uid,
            trace_id,
            fingerprint,
            source,
            event_type,
            topic_name,
            direction,
            payload,
            message
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
        `,
        [
            event.uid,
            event.traceId,
            event.fingerprint || null,
            event.source,
            event.eventType,
            event.topicName || null,
            event.direction || null,
            JSON.stringify(event.payload ?? null),
            event.message
        ]
    )
}
