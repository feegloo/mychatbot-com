import type { RuntimeConfig } from "../types"

/**
 * Creates frontend runtime config from Vite build-time envs.
 */
export function createRuntimeConfig(): RuntimeConfig {
    return {
        appBaseUrl: import.meta.env.VITE_APP_BASE_URL || window.location.origin,
        uploadUrl: import.meta.env.VITE_UPLOAD_FUNCTION_URL || "/api/upload",
        sentryDsn: import.meta.env.VITE_SENTRY_DSN || "",
        sentryEnvironment: import.meta.env.VITE_SENTRY_ENVIRONMENT || "local"
    }
}
