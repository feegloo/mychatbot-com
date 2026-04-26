import * as Sentry from "@sentry/node"
import { nodeProfilingIntegration } from "@sentry/profiling-node"
import type { ServerConfig } from "./types.js"

/**
 * Initializes Sentry for the Node.js Cloud Run server.
 */
export function initSentry(config: ServerConfig): void {
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
 * Sends a debug event to Sentry with structured context.
 */
export function captureDebugMessage(message: string, extra: Record<string, unknown>): void {
    Sentry.captureMessage(message, {
        level: "debug",
        extra
    })
}

/**
 * Captures unexpected runtime exceptions in Sentry.
 */
export function captureException(error: unknown): void {
    Sentry.captureException(error)
}
