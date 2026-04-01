import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:3000/api"
});

export type ConversationStatus = {
  conversationId: string;
  status: "processing" | "ready" | "failed";
  files: Array<{ id: string; originalName: string; mimeType: string; sizeBytes: number }>;
  suggestedQuestions: string[];
};

export async function uploadFiles(files: File[]) {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  const response = await api.post("/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" }
  });
  return response.data as { conversationId: string; url: string; status: string };
}

export async function getConversation(conversationId: string) {
  const response = await api.get(`/conversations/${conversationId}`);
  return response.data as ConversationStatus;
}

export async function askQuestion(conversationId: string, question: string) {
  const response = await api.post("/ask", { conversationId, question });
  return response.data as {
    answer: string;
    citations: Array<{ fileName: string; chunkId: string; text: string; section?: string; page?: number | null }>;
  };
}

export function getStreamUrl(conversationId: string, question: string) {
  const base = (import.meta.env.VITE_API_BASE_URL || "http://localhost:3000/api").replace(/\/api$/, "");
  const url = new URL(`${base}/api/stream-answer`);
  url.searchParams.set("conversationId", conversationId);
  url.searchParams.set("question", question);
  return url.toString();
}
