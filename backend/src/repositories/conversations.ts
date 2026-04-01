import { query } from "../db.js";
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
    `INSERT INTO conversations (id, status, storage_namespace, vector_collection_name, indexing_mode, error_message)
     VALUES ($1, $2, $3, $4, $5, $6)`,
    [
      record.id,
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

export async function getConversation(id: string, role: ConversationRole = "viewer") {
  const conversationResult = await query<ConversationRecord>(
    `SELECT id, status, storage_namespace, vector_collection_name, indexing_mode, error_message
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
    `SELECT id, conversation_id, question, sort_order
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

export async function insertUploadedFile(file: UploadedFileRecord) {
  await query(
    `INSERT INTO uploaded_files (id, conversation_id, original_name, stored_name, mime_type, size_bytes, storage_key)
     VALUES ($1, $2, $3, $4, $5, $6, $7)`,
    [file.id, file.conversation_id, file.original_name, file.stored_name, file.mime_type, file.size_bytes, file.storage_key]
  );
}

export async function replaceSuggestedQuestions(conversationId: string, questions: string[]) {
  await query(`DELETE FROM suggested_questions WHERE conversation_id = $1`, [conversationId]);

  for (const [index, question] of questions.entries()) {
    await query(
      `INSERT INTO suggested_questions (id, conversation_id, question, sort_order)
       VALUES (gen_random_uuid(), $1, $2, $3)`,
      [conversationId, question, index]
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

export async function listAccessRequests(conversationId: string) {
  const result = await query<AccessRequestRecord>(
    `SELECT id, conversation_id, display_name, status, editor_token
     FROM access_requests
     WHERE conversation_id = $1
     ORDER BY created_at DESC`,
    [conversationId]
  );

  return result.rows;
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
}) {
  await query(
    `INSERT INTO conversation_messages (id, conversation_id, role, content, citations_json)
     VALUES (gen_random_uuid(), $1, $2, $3, $4::jsonb)`,
    [
      params.conversationId,
      params.role,
      params.content,
      JSON.stringify(params.citations ?? null)
    ]
  );
}

export async function listConversationMessages(conversationId: string) {
  const result = await query<ConversationMessageRecord>(
    `SELECT id, conversation_id, role, content, citations_json
     FROM conversation_messages
     WHERE conversation_id = $1
     ORDER BY created_at ASC`,
    [conversationId]
  );

  return result.rows;
}
