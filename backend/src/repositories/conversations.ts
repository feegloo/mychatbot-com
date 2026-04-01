import { query } from "../db.js";
import type { ConversationRecord, UploadedFileRecord, SuggestedQuestionRecord } from "../types.js";

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

export async function getConversation(id: string) {
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

  return {
    conversation: conversationResult.rows[0] || null,
    files: filesResult.rows,
    suggestedQuestions: questionsResult.rows
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
