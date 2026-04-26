import { query } from '../db.js'
import { generateShortId } from '../utils/id.js'
import { emitConversationEvent } from '../events.js'
import type {
  ConversationRecord,
  UploadedFileRecord,
  SuggestedQuestionRecord,
  AccessRequestRecord,
  AccessTokenRecord,
  ConversationRole,
  ConversationMessageRecord,
  UserFingerprintRecord,
} from '../types.js'

export async function insertConversation(record: ConversationRecord) {
  await query(
    `INSERT INTO conversations (id, salt, status, storage_namespace, vector_collection_name, indexing_mode, error_message, parent_message_id, parent_conversation_id)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)`,
    [
      record.id,
      record.salt,
      record.status,
      record.storage_namespace,
      record.vector_collection_name,
      record.indexing_mode,
      record.error_message,
      record.parent_message_id || null,
      record.parent_conversation_id || null,
    ],
  )
}

export async function updateConversationStatus(
  id: string,
  status: ConversationRecord['status'],
  errorMessage: string | null = null,
) {
  await query(
    `UPDATE conversations
     SET status = $2, error_message = $3, updated_at = NOW()
     WHERE id = $1`,
    [id, status, errorMessage],
  )
}

export async function updateConversationDisplayName(id: string, displayName: string) {
  await query(
    `UPDATE conversations
     SET display_name = $2, updated_at = NOW()
     WHERE id = $1`,
    [id, displayName],
  )
}

export async function getConversation(id: string, _role: ConversationRole = 'viewer') {
  const conversationResult = await query<ConversationRecord>(
    `SELECT id, salt, display_name, status, storage_namespace, vector_collection_name, indexing_mode, error_message, parent_message_id, parent_conversation_id
     FROM conversations
     WHERE id = $1`,
    [id],
  )

  const conversation = conversationResult.rows[0] || null

  // For thread conversations, fetch files from the parent conversation (via storage_namespace)
  const fileOwner =
    (conversation?.parent_message_id || conversation?.parent_conversation_id) &&
    conversation.storage_namespace !== id
      ? conversation.storage_namespace
      : id

  // Run independent queries in parallel
  const [filesResult, messagesResult, accessRequestsResult] = await Promise.all([
    query<UploadedFileRecord>(
      `SELECT id, conversation_id, original_name, stored_name, mime_type, size_bytes, storage_key, metadata_json
       FROM uploaded_files
       WHERE conversation_id = $1
       ORDER BY created_at ASC`,
      [fileOwner],
    ),
    query<ConversationMessageRecord>(
      `SELECT id, conversation_id, role, content, citations_json, user_id, created_at
       FROM conversation_messages
       WHERE conversation_id = $1
       ORDER BY created_at ASC`,
      [id],
    ),
    query<AccessRequestRecord>(
      `SELECT id, conversation_id, display_name, status, editor_token
       FROM access_requests
       WHERE conversation_id = $1
       ORDER BY created_at DESC`,
      [id],
    ),
  ])

  // For threads, fetch parent message and welcome contents in parallel
  let parentMessage: ConversationMessageRecord | null = null
  let parentWelcomeContents: string[] = []
  const isThread =
    (conversation?.parent_message_id || conversation?.parent_conversation_id) &&
    conversation.storage_namespace !== id

  if (isThread) {
    const parentConvId = conversation.storage_namespace

    const parentQueries: Promise<any>[] = [
      // Fetch parent's welcome message contents for RAG prompt context
      query<ConversationMessageRecord>(
        `SELECT content
         FROM conversation_messages
         WHERE conversation_id = $1 AND role = 'assistant'
           AND citations_json::text LIKE '%_uploadedFileNames%'
         ORDER BY created_at ASC`,
        [parentConvId],
      ),
    ]

    // Also fetch the branched-from message for message-level threads
    if (conversation.parent_message_id) {
      parentQueries.push(
        query<ConversationMessageRecord>(
          `SELECT id, conversation_id, role, content, citations_json, user_id, created_at
           FROM conversation_messages
           WHERE id = $1`,
          [conversation.parent_message_id],
        ),
      )
    }

    const parentResults = await Promise.all(parentQueries)
    parentWelcomeContents = parentResults[0].rows.map((m: ConversationMessageRecord) => m.content)
    if (parentResults[1]) {
      parentMessage = parentResults[1].rows[0] || null
    }
  }

  return {
    conversation,
    files: filesResult.rows,
    suggestedQuestions: [] as SuggestedQuestionRecord[],
    messages: parentMessage ? [parentMessage, ...messagesResult.rows] : messagesResult.rows,
    parentWelcomeContents,
    accessRequests: accessRequestsResult.rows,
  }
}

/**
 * Get the storage_namespace for a conversation.
 * For threads, this points to the parent conversation's directory.
 */
export async function getStorageNamespace(conversationId: string): Promise<string> {
  const result = await query<Pick<ConversationRecord, 'storage_namespace'>>(
    `SELECT storage_namespace FROM conversations WHERE id = $1`,
    [conversationId],
  )
  return result.rows[0]?.storage_namespace || conversationId
}

export async function findStoredName(
  conversationId: string,
  originalName: string,
): Promise<string | null> {
  // First try the given conversation
  const result = await query<UploadedFileRecord>(
    `SELECT stored_name FROM uploaded_files
     WHERE conversation_id = $1 AND original_name = $2
     LIMIT 1`,
    [conversationId, originalName],
  )
  if (result.rows[0]?.stored_name) return result.rows[0].stored_name

  // For thread conversations, also check the parent conversation's files
  const convResult = await query<ConversationRecord>(
    `SELECT storage_namespace, parent_message_id FROM conversations WHERE id = $1`,
    [conversationId],
  )
  const conv = convResult.rows[0]
  if (conv?.parent_message_id && conv.storage_namespace !== conversationId) {
    const parentResult = await query<UploadedFileRecord>(
      `SELECT stored_name FROM uploaded_files
       WHERE conversation_id = $1 AND original_name = $2
       LIMIT 1`,
      [conv.storage_namespace, originalName],
    )
    return parentResult.rows[0]?.stored_name ?? null
  }

  return null
}

export async function getUploadedFilesByOriginalNames(
  conversationId: string,
  originalNames: string[],
) {
  if (!originalNames.length) return []
  const result = await query<UploadedFileRecord>(
    `SELECT id, conversation_id, original_name, stored_name, mime_type, size_bytes, storage_key, metadata_json
     FROM uploaded_files
     WHERE conversation_id = $1
       AND original_name = ANY($2::text[])
     ORDER BY created_at ASC`,
    [conversationId, originalNames],
  )
  return result.rows
}

export async function insertUploadedFile(file: UploadedFileRecord) {
  await query(
    `INSERT INTO uploaded_files (id, conversation_id, original_name, stored_name, mime_type, size_bytes, storage_key)
     VALUES ($1, $2, $3, $4, $5, $6, $7)`,
    [
      file.id,
      file.conversation_id,
      file.original_name,
      file.stored_name,
      file.mime_type,
      file.size_bytes,
      file.storage_key,
    ],
  )
}

export async function updateFileMetadata(
  conversationId: string,
  originalName: string,
  metadata: unknown,
) {
  // PostgreSQL jsonb rejects NUL bytes (\u0000) in JSON strings. EXIF tags
  // like UserComment/componentsConfiguration may contain embedded NULs.
  const serializedMetadata = JSON.stringify(metadata).replace(/\\u0000/g, '')

  await query(
    `UPDATE uploaded_files
     SET metadata_json = $3::jsonb
     WHERE conversation_id = $1 AND original_name = $2`,
    [conversationId, originalName, serializedMetadata],
  )
}

export async function insertAccessToken(record: AccessTokenRecord) {
  await query(
    `INSERT INTO conversation_access_tokens (token, conversation_id, role)
     VALUES ($1, $2, $3)`,
    [record.token, record.conversation_id, record.role],
  )
}

export async function resolveConversationRole(
  conversationId: string,
  token?: string | null,
): Promise<ConversationRole> {
  if (!token) return 'viewer'

  const result = await query<AccessTokenRecord>(
    `SELECT token, conversation_id, role
     FROM conversation_access_tokens
     WHERE conversation_id = $1 AND token = $2`,
    [conversationId, token],
  )

  return result.rows[0]?.role || 'viewer'
}

export async function createAccessRequest(record: AccessRequestRecord) {
  await query(
    `INSERT INTO access_requests (id, conversation_id, display_name, status, editor_token)
     VALUES ($1, $2, $3, $4, $5)`,
    [record.id, record.conversation_id, record.display_name, record.status, record.editor_token],
  )
}

export async function getAccessRequest(conversationId: string, requestId: string) {
  const result = await query<AccessRequestRecord>(
    `SELECT id, conversation_id, display_name, status, editor_token
     FROM access_requests
     WHERE conversation_id = $1 AND id = $2`,
    [conversationId, requestId],
  )

  return result.rows[0] || null
}

export async function approveAccessRequest(
  conversationId: string,
  requestId: string,
  editorToken: string,
) {
  await query(
    `UPDATE access_requests
     SET status = 'approved', editor_token = $3, updated_at = NOW()
     WHERE conversation_id = $1 AND id = $2`,
    [conversationId, requestId, editorToken],
  )
}

export async function insertConversationMessage(params: {
  conversationId: string
  role: 'user' | 'assistant'
  content: string
  citations?: unknown
  userId?: number
}): Promise<string> {
  const id = generateShortId()
  await query(
    `INSERT INTO conversation_messages (id, conversation_id, role, content, citations_json, user_id)
     VALUES ($1, $2, $3, $4, $5::jsonb, $6)`,
    [
      id,
      params.conversationId,
      params.role,
      params.content,
      JSON.stringify(params.citations ?? null),
      params.userId ?? 0,
    ],
  )
  // Fan out to any SSE subscribers so clients (including other browser tabs)
  // can refresh without the 1s polling fallback.
  emitConversationEvent(params.conversationId, {
    event: 'message_appended',
    data: { messageId: id, role: params.role },
  })
  return id
}

/**
 * Append text to an existing assistant message's content and replace its
 * citations payload. Used by the auto-image background job that augments a
 * just-returned answer with a companion image.
 */
export async function appendToMessageContent(params: {
  messageId: string
  contentToAppend: string
  citations: unknown
}) {
  await query(
    `UPDATE conversation_messages
     SET content = content || $2,
         citations_json = $3::jsonb
     WHERE id = $1`,
    [params.messageId, params.contentToAppend, JSON.stringify(params.citations ?? null)],
  )
}

export async function updateConversationMessageContent(
  messageId: string,
  content: string,
): Promise<void> {
  await query(
    `UPDATE conversation_messages SET content = $2 WHERE id = $1`,
    [messageId, content],
  )
}

export async function getMessageById(messageId: string) {
  const msgResult = await query<ConversationMessageRecord & { display_name: string | null }>(
    `SELECT m.id, m.conversation_id, m.role, m.content, m.citations_json, c.display_name
     FROM conversation_messages m
     JOIN conversations c ON c.id = m.conversation_id
     WHERE m.id = $1`,
    [messageId],
  )
  return msgResult.rows[0] || null
}

export async function getConversationSummaries(conversationIds: string[]) {
  if (!conversationIds.length) return []

  const placeholders = conversationIds.map((_, i) => `$${i + 1}`).join(', ')
  const result = await query<Pick<ConversationRecord, 'id' | 'display_name' | 'status'>>(
    `SELECT id, display_name, status
     FROM conversations
     WHERE id IN (${placeholders})
     ORDER BY updated_at DESC`,
    conversationIds,
  )

  const fileResults = await query<Pick<UploadedFileRecord, 'conversation_id' | 'original_name'>>(
    `SELECT conversation_id, original_name
     FROM uploaded_files
     WHERE conversation_id IN (${placeholders})
     ORDER BY created_at ASC`,
    conversationIds,
  )

  const filesByConversation = new Map<string, string[]>()
  for (const row of fileResults.rows) {
    const list = filesByConversation.get(row.conversation_id) || []
    list.push(row.original_name)
    filesByConversation.set(row.conversation_id, list)
  }

  return result.rows.map((row) => ({
    ...row,
    fileNames: filesByConversation.get(row.id) || [],
  }))
}

/**
 * Resolve a browser fingerprint to a userId.
 * If fingerprint doesn't exist yet, create a new user with auto-incremented userId.
 */
export async function resolveUserByFingerprint(
  fingerprint: string,
  userAgent?: string,
): Promise<number> {
  // Try to find existing
  const existing = await query<UserFingerprintRecord>(
    `SELECT user_id FROM user_fingerprints WHERE fingerprint = $1`,
    [fingerprint],
  )
  if (existing.rows[0]) {
    return existing.rows[0].user_id
  }
  // Insert new (SERIAL auto-increments user_id)
  const inserted = await query<UserFingerprintRecord>(
    `INSERT INTO user_fingerprints (fingerprint, user_agent)
     VALUES ($1, $2)
     ON CONFLICT (fingerprint) DO NOTHING
     RETURNING user_id`,
    [fingerprint, userAgent ?? null],
  )
  if (inserted.rows[0]) {
    return inserted.rows[0].user_id
  }
  // Race condition: another request inserted first, re-fetch
  const refetch = await query<UserFingerprintRecord>(
    `SELECT user_id FROM user_fingerprints WHERE fingerprint = $1`,
    [fingerprint],
  )
  return refetch.rows[0].user_id
}

/**
 * Get all thread conversations (children) for a given parent message.
 */
export async function getThreadsForMessage(messageId: string) {
  const result = await query<ConversationRecord & { message_count: number; last_user_id: number }>(
    `SELECT c.id, c.display_name, c.status, c.parent_message_id, c.created_at,
            COUNT(m.id)::int as message_count,
            COALESCE(MAX(m.user_id), 0) as last_user_id
     FROM conversations c
     LEFT JOIN conversation_messages m ON m.conversation_id = c.id
     WHERE c.parent_message_id = $1
     GROUP BY c.id
     ORDER BY c.created_at ASC`,
    [messageId],
  )
  return result.rows
}

/**
 * Count total thread replies for a given parent message.
 */
export async function getThreadReplyCount(messageId: string): Promise<number> {
  const result = await query<{ count: string }>(
    `SELECT COUNT(*)::text as count
     FROM conversation_messages m
     JOIN conversations c ON c.id = m.conversation_id
     WHERE c.parent_message_id = $1`,
    [messageId],
  )
  return parseInt(result.rows[0]?.count || '0', 10)
}

/**
 * Get thread reply counts for multiple parent message IDs at once.
 */
export async function getThreadReplyCountsForMessages(
  messageIds: string[],
): Promise<Map<string, number>> {
  if (!messageIds.length) return new Map()
  const placeholders = messageIds.map((_, i) => `$${i + 1}`).join(', ')
  const result = await query<{ parent_message_id: string; count: string }>(
    `SELECT c.parent_message_id, COUNT(m.id)::text as count
     FROM conversations c
     JOIN conversation_messages m ON m.conversation_id = c.id
     WHERE c.parent_message_id IN (${placeholders})
     GROUP BY c.parent_message_id`,
    messageIds,
  )
  const map = new Map<string, number>()
  for (const row of result.rows) {
    map.set(row.parent_message_id, parseInt(row.count, 10))
  }
  return map
}

/**
 * Get all thread conversations branched from a shared conversation (via parent_conversation_id).
 */
export async function getThreadsForConversation(conversationId: string) {
  const result = await query<ConversationRecord & { message_count: number; last_user_id: number }>(
    `SELECT c.id, c.display_name, c.status, c.parent_conversation_id, c.created_at,
            COUNT(m.id)::int as message_count,
            COALESCE(MAX(m.user_id), 0) as last_user_id
     FROM conversations c
     LEFT JOIN conversation_messages m ON m.conversation_id = c.id
     WHERE c.parent_conversation_id = $1
     GROUP BY c.id
     ORDER BY c.created_at ASC`,
    [conversationId],
  )
  return result.rows
}

/**
 * Count total replies across all conversation-level threads for a given conversation.
 */
export async function getConversationThreadReplyCount(conversationId: string): Promise<number> {
  const result = await query<{ count: string }>(
    `SELECT COUNT(m.id)::text as count
     FROM conversation_messages m
     JOIN conversations c ON c.id = m.conversation_id
     WHERE c.parent_conversation_id = $1`,
    [conversationId],
  )
  return parseInt(result.rows[0]?.count || '0', 10)
}
