import { randomUUID } from "node:crypto"
import type { Request } from "express"

/**
 * Parses comma-separated CORS origins from env.
 */
export function parseAllowedOrigins(value: string | undefined): string[] {
    return String(value || "")
        .split(",")
        .map((origin) => origin.trim())
        .filter(Boolean)
}

/**
 * Reads request trace id from headers, query, body, or creates a new one.
 */
export function getTraceId(req: Request): string {
    return readStringHeader(req, "x-trace-id") || readStringQuery(req, "traceId") || readStringBody(req, "traceId") || randomUUID()
}

/**
 * Reads browser fingerprint from headers, query, body, or creates a fallback id.
 */
export function getFingerprint(req: Request): string {
    return readStringHeader(req, "fingerprint") || readStringQuery(req, "fingerprint") || readStringBody(req, "fingerprint") || "anonymous"
}

/**
 * Reads question string from JSON request body.
 */
export function getQuestion(req: Request): string {
    const body = req.body as { question?: unknown } | undefined
    return typeof body?.question === "string" ? body.question.trim() : ""
}

/**
 * Reads string header from Express request.
 */
export function readStringHeader(req: Request, name: string): string | null {
    const value = req.header(name)
    return value ? String(value) : null
}

/**
 * Reads string query value from Express request.
 */
export function readStringQuery(req: Request, name: string): string | null {
    const value = req.query[name]
    return typeof value === "string" ? value : null
}

/**
 * Reads string body value from Express request.
 */
export function readStringBody(req: Request, name: string): string | null {
    const body = req.body as Record<string, unknown> | undefined
    const value = body?.[name]
    return typeof value === "string" ? value : null
}

/**
 * Creates UTC timestamp for HTTP and SSE payloads.
 */
export function nowIso(): string {
    return new Date().toISOString()
}
