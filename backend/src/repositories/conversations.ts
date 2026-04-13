import { query } from "../db.js";
import { generateShortId } from "../utils/id.js";
import type {
  ConversationRecord,
  UploadedFileRecord,
  SuggestedQuestionRecord,
  AccessRequestRecord,
  AccessTokenRecord,
  ConversationRole,
  ConversationMessageRecord
} from "../types.js";

export async function insertConversation(record: ConversationRecord) {
  await query(
    `INSERT INTO conversations (id, salt, status, storage_namespace, vector_collection_name, indexing_mode, error_message)
     VALUES ($1, $2, $3, $4, $5, $6, $7)`,
    [
      record.id,
      record.salt,
      record.status,
      record.storage_namespace,
      record.vector_collection_name,
      record.indexing_mode,
      record.error_message
    ]
  );
}

export async function updateConversationStatus(id: string, status: ConversationRecord["status"], errorMessage: string | null = null) {
  await query(
    `UPDATE conversations
     SET status = $2, error_message = $3, updated_at = NOW()
     WHERE id = $1`,
    [id, status, errorMessage]
  );
}

export async function updateConversationDisplayName(id: string, displayName: string) {
  await query(
    `UPDATE conversations
     SET display_name = $2, updated_at = NOW()
     WHERE id = $1`,
    [id, displayName]
  );
}

export async function getConversation(id: string, role: ConversationRole = "viewer") {
  const conversationResult = await query<ConversationRecord>(
    `SELECT id, salt, display_name, status, storage_namespace, vector_collection_name, indexing_mode, error_message
     FROM conversations
     WHERE id = $1`,
    [id]
  );

  const filesResult = await query<UploadedFileRecord>(
    `SELECT id, conversation_id, original_name, stored_name, mime_type, size_bytes, storage_key
     FROM uploaded_files
     WHERE conversation_id = $1
     ORDER BY created_at ASC`,
    [id]
  );

  const questionsResult = await query<SuggestedQuestionRecord>(
    `SELECT id, conversation_id, message_id, question, sort_order
     FROM suggested_questions
     WHERE conversation_id = $1
     ORDER BY sort_order ASC, created_at ASC`,
    [id]
  );

  const messagesResult = await query<ConversationMessageRecord>(
    `SELECT id, conversation_id, role, content, citations_json
     FROM conversation_messages
     WHERE conversation_id = $1
     ORDER BY created_at ASC`,
    [id]
  );

  const accessRequestsResult = await query<AccessRequestRecord>(
    `SELECT id, conversation_id, display_name, status, editor_token
     FROM access_requests
     WHERE conversation_id = $1
     ORDER BY created_at DESC`,
    [id]
  );

  return {
    conversation: conversationResult.rows[0] || null,
    files: filesResult.rows,
    suggestedQuestions: questionsResult.rows,
    messages: messagesResult.rows,
    accessRequests: accessRequestsResult.rows
  };
}

export async function findStoredName(conversationId: string, originalName: string): Promise<string | null> {
  const result = await query<UploadedFileRecord>(
    `SELECT stored_name FROM uploaded_files
     WHERE conversation_id = $1 AND original_name = $2
     LIMIT 1`,
    [conversationId, originalName]
  );
  return result.rows[0]?.stored_name ?? null;
}

export async function insertUploadedFile(file: UploadedFileRecord) {
  await query(
    `INSERT INTO uploaded_files (id, conversation_id, original_name, stored_name, mime_type, size_bytes, storage_key)
     VALUES ($1, $2, $3, $4, $5, $6, $7)`,
    [file.id, file.conversation_id, file.original_name, file.stored_name, file.mime_type, file.size_bytes, file.storage_key]
  );
}

export async function replaceSuggestedQuestions(conversationId: string, questions: string[], messageId?: string) {
  await query(`DELETE FROM suggested_questions WHERE conversation_id = $1`, [conversationId]);

  for (const [index, question] of questions.entries()) {
    await query(
      `INSERT INTO suggested_questions (id, conversation_id, message_id, question, sort_order)
       VALUES (gen_random_uuid(), $1, $2, $3, $4)`,
      [conversationId, messageId || null, question, index]
    );
  }
}

export async function appendSuggestedQuestions(conversationId: string, questions: string[], messageId?: string) {
  // Get current max sort_order
  const result = await query<{ max: number | null }>(
    `SELECT MAX(sort_order) as max FROM suggested_questions WHERE conversation_id = $1`,
    [conversationId]
  );

  const startIndex = (result.rows[0]?.max ?? -1) + 1;

  // Add new questions without deleting old ones
  for (const [index, question] of questions.entries()) {
    await query(
      `INSERT INTO suggested_questions (id, conversation_id, message_id, question, sort_order)
       VALUES (gen_random_uuid(), $1, $2, $3, $4)`,
      [conversationId, messageId || null, question, startIndex + index]
    );
  }
}

export async function insertAccessToken(record: AccessTokenRecord) {
  await query(
    `INSERT INTO conversation_access_tokens (token, conversation_id, role)
     VALUES ($1, $2, $3)`,
    [record.token, record.conversation_id, record.role]
  );
}

export async function resolveConversationRole(conversationId: string, token?: string | null): Promise<ConversationRole> {
  if (!token) return "viewer";

  const result = await query<AccessTokenRecord>(
    `SELECT token, conversation_id, role
     FROM conversation_access_tokens
     WHERE conversation_id = $1 AND token = $2`,
    [conversationId, token]
  );

  return result.rows[0]?.role || "viewer";
}

export async function createAccessRequest(record: AccessRequestRecord) {
  await query(
    `INSERT INTO access_requests (id, conversation_id, display_name, status, editor_token)
     VALUES ($1, $2, $3, $4, $5)`,
    [record.id, record.conversation_id, record.display_name, record.status, record.editor_token]
  );
}

export async function getAccessRequest(conversationId: string, requestId: string) {
  const result = await query<AccessRequestRecord>(
    `SELECT id, conversation_id, display_name, status, editor_token
     FROM access_requests
     WHERE conversation_id = $1 AND id = $2`,
    [conversationId, requestId]
  );

  return result.rows[0] || null;
}

export async function approveAccessRequest(conversationId: string, requestId: string, editorToken: string) {
  await query(
    `UPDATE access_requests
     SET status = 'approved', editor_token = $3, updated_at = NOW()
     WHERE conversation_id = $1 AND id = $2`,
    [conversationId, requestId, editorToken]
  );
}

export async function insertConversationMessage(params: {
  conversationId: string;
  role: "user" | "assistant";
  content: string;
  citations?: unknown;
}): Promise<string> {
  const id = generateShortId();
  await query(
    `INSERT INTO conversation_messages (id, conversation_id, role, content, citations_json)
     VALUES ($1, $2, $3, $4, $5::jsonb)`,
    [
      id,
      params.conversationId,
      params.role,
      params.content,
      JSON.stringify(params.citations ?? null)
    ]
  );
  return id;
}

export async function getMessageById(messageId: string) {
  const msgResult = await query<ConversationMessageRecord & { display_name: string | null }>(
    `SELECT m.id, m.conversation_id, m.role, m.content, m.citations_json, c.display_name
     FROM conversation_messages m
     JOIN conversations c ON c.id = m.conversation_id
     WHERE m.id = $1`,
    [messageId]
  );
  return msgResult.rows[0] || null;
}

export async function getConversationSummaries(conversationIds: string[]) {
  if (!conversationIds.length) return [];

  const placeholders = conversationIds.map((_, i) => `$${i + 1}`).join(", ");
  const result = await query<Pick<ConversationRecord, "id" | "display_name" | "status">>(
    `SELECT id, display_name, status
     FROM conversations
     WHERE id IN (${placeholders})
     ORDER BY updated_at DESC`,
    conversationIds
  );

  const fileResults = await query<Pick<UploadedFileRecord, "conversation_id" | "original_name">>(
    `SELECT conversation_id, original_name
     FROM uploaded_files
     WHERE conversation_id IN (${placeholders})
     ORDER BY created_at ASC`,
    conversationIds
  );

  const filesByConversation = new Map<string, string[]>();
  for (const row of fileResults.rows) {
    const list = filesByConversation.get(row.conversation_id) || [];
    list.push(row.original_name);
    filesByConversation.set(row.conversation_id, list);
  }

  return result.rows.map((row) => ({
    ...row,
    fileNames: filesByConversation.get(row.id) || []
  }));
}
