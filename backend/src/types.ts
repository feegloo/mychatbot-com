export type ConversationStatus = "processing" | "ready" | "failed";

export type ConversationRecord = {
  id: string;
  status: ConversationStatus;
  storage_namespace: string;
  vector_collection_name: string;
  indexing_mode: string;
  error_message: string | null;
};

export type UploadedFileRecord = {
  id: string;
  conversation_id: string;
  original_name: string;
  stored_name: string;
  mime_type: string;
  size_bytes: number;
  storage_key: string;
};

export type SuggestedQuestionRecord = {
  id: string;
  conversation_id: string;
  question: string;
  sort_order: number;
};
