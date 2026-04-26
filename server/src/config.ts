import {
    DEFAULT_ASK_TIMEOUT_MS,
    DEFAULT_ANSWER_SUBSCRIPTION,
    DEFAULT_FRONTEND_DIST_PATH,
    DEFAULT_PORT,
    DEFAULT_PUBLIC_APP_DOMAIN,
    DEFAULT_WORKER_TOPIC
} from "./const.js"
import type { ServerConfig } from "./types.js"
import { parseAllowedOrigins } from "./utils.js"

/**
 * Reads server runtime configuration from environment variables.
 */
export function createConfig(): ServerConfig {
    return {
        port: Number(process.env.PORT || DEFAULT_PORT),
        frontendDistPath: process.env.FRONTEND_DIST_PATH || DEFAULT_FRONTEND_DIST_PATH,
        workerTopic: process.env.PUBSUB_TOPIC || DEFAULT_WORKER_TOPIC,
        answerSubscription: process.env.PUBSUB_ANSWER_SUBSCRIPTION || DEFAULT_ANSWER_SUBSCRIPTION,
        askTimeoutMs: Number(process.env.ASK_TIMEOUT_MS || DEFAULT_ASK_TIMEOUT_MS),
        databaseUrl: process.env.DATABASE_URL,
        sentryDsn: process.env.SENTRY_DSN,
        sentryEnvironment: process.env.SENTRY_ENVIRONMENT || "production",
        sentryRelease: process.env.SENTRY_RELEASE || "chatrag@local",
        allowedOrigins: parseAllowedOrigins(process.env.ALLOWED_ORIGINS),
        publicAppDomain: process.env.PUBLIC_APP_DOMAIN || DEFAULT_PUBLIC_APP_DOMAIN
    }
}
