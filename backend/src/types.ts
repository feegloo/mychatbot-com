export type ConversationStatus = "uploading" | "processing" | "ready" | "failed";
export type ConversationRole = "owner" | "editor" | "viewer";

export type ConversationRecord = {
  id: string;
  salt: string;
  display_name: string | null;
  status: ConversationStatus;
  storage_namespace: string;
  vector_collection_name: string;
  indexing_mode: string;
  error_message: string | null;
  parent_message_id: string | null;
  parent_conversation_id: string | null;
};

export type UploadedFileRecord = {
  id: string;
  conversation_id: string;
  original_name: string;
  stored_name: string;
  mime_type: string;
  size_bytes: number;
  storage_key: string;
  metadata_json?: any;
};

export type SuggestedQuestionRecord = {
  id: string;
  conversation_id: string;
  message_id: string | null;
  question: string;
  sort_order: number;
};

export type AccessRequestRecord = {
  id: string;
  conversation_id: string;
  display_name: string;
  status: "pending" | "approved" | "rejected";
  editor_token: string | null;
};

export type AccessTokenRecord = {
  token: string;
  conversation_id: string;
  role: "owner" | "editor";
};

export type ConversationMessageRecord = {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  citations_json: any;
  user_id: number;
  created_at?: string;
};

export type UserFingerprintRecord = {
  fingerprint: string;
  user_id: number;
};
