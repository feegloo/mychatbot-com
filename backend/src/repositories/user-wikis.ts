/**
 * Repository for per-user master knowledge wikis.
 *
 * The wiki is built by aggregating per-conversation Section-3a "idea files"
 * (internal_kind='wiki' messages) across all conversations where the user
 * has sent at least one message. The Python /user-wiki endpoint synthesises
 * them into a cross-topic master wiki stored here.
 *
 * Rebuild is triggered lazily from ask.ts with a 30-minute cooldown so we
 * don't call the LLM on every question.
 */

import { query } from '../db.js'

/** Returns the stored master wiki content for a user, or null if none exists. */
export async function getUserWiki(userId: number): Promise<string | null> {
  const result = await query<{ content: string }>(
    'SELECT content FROM user_wikis WHERE user_id = $1',
    [userId],
  )
  return result.rows[0]?.content ?? null
}

/** Returns true if the user wiki is missing or was last built > 30 minutes ago. */
export async function isUserWikiStale(userId: number): Promise<boolean> {
  const result = await query<{ stale: boolean }>(
    `SELECT (updated_at < NOW() - INTERVAL '30 minutes') AS stale
     FROM user_wikis
     WHERE user_id = $1`,
    [userId],
  )
  // No row → stale (never built)
  if (result.rows.length === 0) return true
  return result.rows[0].stale
}

/** Upserts the master wiki for a user. */
export async function upsertUserWiki(
  userId: number,
  content: string,
  sourceCount: number,
): Promise<void> {
  await query(
    `INSERT INTO user_wikis (user_id, content, source_count, updated_at)
     VALUES ($1, $2, $3, NOW())
     ON CONFLICT (user_id) DO UPDATE
       SET content      = EXCLUDED.content,
           source_count = EXCLUDED.source_count,
           updated_at   = NOW()`,
    [userId, content, sourceCount],
  )
}

/**
 * Returns all per-conversation wikis (Section-3a internal messages) for a
 * user — i.e., conversations where the user has sent at least one message.
 *
 * Each row: { conversation_id: string, content: string }
 */
export async function getConversationWikisForUser(
  userId: number,
): Promise<{ conversationId: string; content: string }[]> {
  const result = await query<{ conversation_id: string; content: string }>(
    `SELECT DISTINCT ON (w.conversation_id)
            w.conversation_id,
            w.content
     FROM conversation_messages w
     WHERE w.is_internal = TRUE
       AND w.internal_kind = 'wiki'
       -- Only include conversations where this user has interacted
       AND EXISTS (
         SELECT 1
         FROM conversation_messages um
         WHERE um.conversation_id = w.conversation_id
           AND um.user_id = $1
           AND um.user_id > 0
       )
     ORDER BY w.conversation_id, w.created_at DESC`,
    [userId],
  )
  return result.rows.map((r) => ({
    conversationId: r.conversation_id,
    content: r.content,
  }))
}
