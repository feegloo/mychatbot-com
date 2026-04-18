import axios from "axios";

const api = axios.create({
  // @ts-ignore
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:3000/api"
});

const TOKENS_STORAGE_KEY = "conversation-token";

type TokensMap = {
  [conversationId: string]: string;
};

function getTokensMap(): TokensMap {
  try {
    const stored = localStorage.getItem(TOKENS_STORAGE_KEY);
    return stored ? JSON.parse(stored) : {};
  } catch {
    return {};
  }
}

function saveTokensMap(tokens: TokensMap) {
  localStorage.setItem(TOKENS_STORAGE_KEY, JSON.stringify(tokens));
}

export function saveConversationToken(conversationId: string, token: string) {
  const tokens = getTokensMap();
  tokens[conversationId] = token;
  saveTokensMap(tokens);
}

export function getConversationToken(conversationId: string) {
  const tokens = getTokensMap();
  return tokens[conversationId] || "";
}

export function getStoredConversationIds(): string[] {
  return Object.keys(getTokensMap());
}

export type ConversationSummary = {
  conversationId: string;
  displayName: string | null;
  status: "processing" | "ready" | "failed";
  fileNames: string[];
};

export async function listMyConversations(): Promise<ConversationSummary[]> {
  const tokens = getTokensMap();
  const ids = Object.keys(tokens);
  if (!ids.length) return [];

  const response = await api.post("/conversations/batch", { conversationIds: ids });
  const conversations = (response.data as { conversations: ConversationSummary[] }).conversations;

  // Remove stale tokens for conversations that no longer exist in the DB
  const returnedIds = new Set(conversations.map((c) => c.conversationId));
  const staleIds = ids.filter((id) => !returnedIds.has(id));
  if (staleIds.length) {
    const updated = getTokensMap();
    for (const id of staleIds) delete updated[id];
    saveTokensMap(updated);
  }

  return conversations;
}

function authHeaders(conversationId: string) {
  const token = getConversationToken(conversationId);
  return token ? { "x-conversation-token": token } : {};
}

export type ChatMessage = {
  id?: string;
  role: "user" | "assistant";
  content: string;
  citations?: Array<{ fileName: string; chunkId: string; text: string; section?: string; page?: number | null; imageName?: string }>;
  uploadedFileNames?: string[];
  suggestedQuestions?: string[];
  userId?: number;
  threadReplyCount?: number;
  isParentMessage?: boolean;
};

export type ConversationStatus = {
  conversationId: string;
  displayName: string | null;
  status: "processing" | "ready" | "failed";
  role: "owner" | "editor" | "viewer";
  parentMessageId: string | null;
  parentConversationId: string | null;
  storageNamespace?: string;
  conversationThreadCount?: number;
  files: Array<{ id: string; originalName: string; mimeType: string; sizeBytes: number; metadata?: any }>;
  messages: ChatMessage[];
  suggestedQuestions: string[];
  accessRequests: Array<{ id: string; displayName: string; status: "pending" | "approved" | "rejected" }>;
  errorMessage?: string | null;
};

export async function uploadFiles(files: File[]) {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  const response = await api.post("/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" }
  });
  return response.data as { conversationId: string; url: string; status: string; ownerPassword: string };
}

export async function uploadUrl(url: string) {
  const response = await api.post("/upload-url", { url });
  return response.data as { conversationId: string; url: string; status: string; ownerPassword: string };
}

export async function createConversation() {
  const response = await api.post("/conversations");
  return response.data as { conversationId: string; url: string; status: string; ownerPassword: string };
}

export async function uploadMoreFiles(conversationId: string, files: File[]) {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  const response = await api.post(`/conversations/${conversationId}/files`, formData, {
    headers: {
      "Content-Type": "multipart/form-data",
      ...authHeaders(conversationId)
    }
  });
  return response.data as { conversationId: string; status: string };
}

export async function getConversation(conversationId: string) {
  const response = await api.get(`/conversations/${conversationId}`, {
    headers: authHeaders(conversationId)
  });
  return response.data as ConversationStatus;
}

export async function askQuestion(conversationId: string, question: string, userId?: number) {
  const response = await api.post("/ask", { conversationId, question, ...(userId ? { userId } : {}) }, {
    headers: authHeaders(conversationId)
  });
  return response.data as {
    answer: string;
    citations: Array<{ fileName: string; chunkId: string; text: string; section?: string; page?: number | null }>;
    userMessageId?: string;
    assistantMessageId?: string;
  };
}

export async function generateImage(conversationId: string, question: string, userId?: number) {
  const response = await api.post("/generate-image", { conversationId, question, ...(userId ? { userId } : {}) }, {
    headers: authHeaders(conversationId)
  });
  return response.data as {
    answer: string;
    citations: Array<{ fileName: string; chunkId: string; text: string; section?: string; page?: number | null }>;
    userMessageId?: string;
    assistantMessageId?: string;
    generatedImage?: {
      fileName: string;
      imagePrompt: string;
      revisedPrompt: string;
    };
  };
}

function getBaseUrl() {
  // @ts-ignore
  return (import.meta.env.VITE_API_BASE_URL || "http://localhost:3000/api").replace(/\/api$/, "");
}

export function getStorageUrl(conversationId: string, fileName: string) {
  return `${getBaseUrl()}/api/storage/${conversationId}/${encodeURIComponent(fileName)}`;
}

export async function requestUploadAccess(conversationId: string, displayName: string) {
  const response = await api.post(`/conversations/${conversationId}/access-requests`, { displayName });
  return response.data as { requestId: string; status: "pending" };
}

export async function getUploadAccessRequest(conversationId: string, requestId: string) {
  const response = await api.get(`/conversations/${conversationId}/access-requests/${requestId}`);
  return response.data as { requestId: string; status: "pending" | "approved" | "rejected"; editorPassword: string | null };
}

export async function approveUploadAccess(conversationId: string, requestId: string) {
  const response = await api.post(
    `/conversations/${conversationId}/access-requests/${requestId}/approve`,
    {},
    { headers: authHeaders(conversationId) }
  );
  return response.data as { requestId: string; status: "approved" };
}

export async function renameConversation(conversationId: string, displayName: string) {
  const response = await api.patch(
    `/conversations/${conversationId}/name`,
    { displayName },
    { headers: authHeaders(conversationId) }
  );
  return response.data as { displayName: string };
}

export type SharedMessage = {
  id: string;
  conversationId: string;
  displayName: string | null;
  role: "assistant";
  content: string;
  citations: ChatMessage["citations"];
  uploadedFileNames?: string[];
  files?: ConversationStatus["files"];
};

export async function getSharedMessage(messageId: string) {
  const response = await api.get(`/messages/${messageId}`);
  return response.data as SharedMessage;
}

export async function getDebugTables(username: string, password: string, offset = 0) {
  const response = await api.get("/debug/tables", {
    auth: { username, password },
    params: { offset },
  });
  return response.data as {
    conversations: Record<string, unknown>[];
    conversation_messages: Record<string, unknown>[];
    suggested_questions: Record<string, unknown>[];
    uploaded_files: Record<string, unknown>[];
    user_fingerprints: Record<string, unknown>[];
    conversation_access_tokens: Record<string, unknown>[];
    access_requests: Record<string, unknown>[];
    users: Record<string, unknown>[];
  };
}

export async function translateTexts(texts: string[], targetLang: string, sourceLang?: string) {
  const body: { texts: string[]; targetLang: string; sourceLang?: string } = { texts, targetLang };
  if (sourceLang) body.sourceLang = sourceLang;
  const response = await api.post("/translate", body);
  return response.data as { translations: string[] };
}

export async function detectLanguage(text: string) {
  const response = await api.post("/detect-language", { text });
  return response.data as { language: string; confidence: number };
}

export async function synthesizeSpeech(text: string, language?: string): Promise<Blob> {
  const body: { text: string; language?: string } = { text };
  if (language) body.language = language;
  const response = await api.post("/synthesize", body, {
    responseType: "blob",
  });
  return response.data as Blob;
}

export type WordCaption = {
  word: string;
  start: number;
  end: number;
};

export async function synthesizeSpeechWithCaptions(
  text: string,
  language?: string,
  translateTo?: string,
): Promise<{ audio: Blob; captions: WordCaption[] | null; translatedText?: string }> {
  const body: { text: string; language?: string; translateTo?: string } = { text };
  if (language) body.language = language;
  if (translateTo) body.translateTo = translateTo;

  const response = await api.post("/synthesize-with-captions", body);
  const data = response.data as {
    audio: string;
    captions: WordCaption[] | null;
    translatedText?: string;
  };

  // Decode base64 audio to Blob
  const binaryStr = atob(data.audio);
  const bytes = new Uint8Array(binaryStr.length);
  for (let i = 0; i < binaryStr.length; i++) {
    bytes[i] = binaryStr.charCodeAt(i);
  }

  return {
    audio: new Blob([bytes], { type: "audio/mpeg" }),
    captions: data.captions ?? null,
    translatedText: data.translatedText,
  };
}

export async function resolveFingerprint(fingerprint: string) {
  const response = await api.post("/fingerprint", { fingerprint });
  return response.data as { userId: number };
}

export type ThreadSummary = {
  conversationId: string;
  displayName: string | null;
  messageCount: number;
  lastUserId: number;
};

export async function getMessageThreads(messageId: string) {
  const response = await api.get(`/messages/${messageId}/threads`);
  return response.data as { threads: ThreadSummary[] };
}

export async function createThread(messageId: string, userId: number) {
  const response = await api.post(`/messages/${messageId}/threads`, { userId });
  return response.data as { conversationId: string; ownerPassword: string; url: string };
}

export async function getConversationThreads(conversationId: string) {
  const response = await api.get(`/conversations/${conversationId}/threads`);
  return response.data as { threads: ThreadSummary[] };
}

export async function createConversationThread(conversationId: string, userId: number) {
  const response = await api.post(`/conversations/${conversationId}/threads`, { userId });
  return response.data as { conversationId: string; ownerPassword: string; url: string };
}
