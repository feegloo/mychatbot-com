import pg from "pg"
import type { Pool } from "pg"
import type { MetadataEventInput, ServerConfig } from "./types.js"

const { Pool: PgPool } = pg

/**
 * Creates PostgreSQL pool or returns null when DATABASE_URL is not configured.
 */
export function createDatabasePool(config: ServerConfig): Pool | null {
    if (!config.databaseUrl) {
        return null
    }

    return new PgPool({
        connectionString: config.databaseUrl,
        max: 4,
        idleTimeoutMillis: 30_000
    })
}

/**
 * Inserts one debug event into conversations_metadatas.
 */
export async function insertConversationMetadata(pool: Pool | null, event: MetadataEventInput): Promise<void> {
    if (!pool) {
        return
    }

    await ensureConversationExists(pool, event.uid, event.traceId)

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

/**
 * Ensures metadata has a valid foreign key target in conversations.
 */
async function ensureConversationExists(pool: Pool, uid: string, traceId: string): Promise<void> {
    await pool.query(
        `
        INSERT INTO conversations(uid, trace_id, status)
        VALUES ($1, $2, 'metadata-only')
        ON CONFLICT (uid) DO NOTHING
        `,
        [uid, traceId]
    )
}
