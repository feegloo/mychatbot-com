import * as Sentry from "@sentry/browser"
import type { RuntimeConfig } from "../types"

/**
 * Initializes Sentry browser SDK when VITE_SENTRY_DSN is configured.
 */
export function initSentry(config: RuntimeConfig): void {
    if (!config.sentryDsn) {
        return
    }

    Sentry.init({
        dsn: config.sentryDsn,
        environment: config.sentryEnvironment,
        tracesSampleRate: 1.0,
        debug: true
    })
}

/**
 * Sends debug breadcrumb visible in Sentry trace explorer.
 */
export function captureFrontendDebug(message: string, data: Record<string, unknown>): void {
    Sentry.addBreadcrumb({
        category: "frontend",
        level: "debug",
        message,
        data
    })
}
