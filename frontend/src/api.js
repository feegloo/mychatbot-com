import axios from "axios";
const api = axios.create({
    // @ts-ignore
    baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:3000/api"
});
const TOKENS_STORAGE_KEY = "conversation-token";
function getTokensMap() {
    try {
        const stored = localStorage.getItem(TOKENS_STORAGE_KEY);
        return stored ? JSON.parse(stored) : {};
    }
    catch {
        return {};
    }
}
function saveTokensMap(tokens) {
    localStorage.setItem(TOKENS_STORAGE_KEY, JSON.stringify(tokens));
}
export function saveConversationToken(conversationId, token) {
    const tokens = getTokensMap();
    tokens[conversationId] = token;
    saveTokensMap(tokens);
}
export function getConversationToken(conversationId) {
    const tokens = getTokensMap();
    return tokens[conversationId] || "";
}
export function getStoredConversationIds() {
    return Object.keys(getTokensMap());
}
export async function listMyConversations() {
    const tokens = getTokensMap();
    const entries = Object.entries(tokens);
    if (!entries.length)
        return [];
    const response = await api.post("/conversations/batch", {
        conversations: entries.map(([conversationId, token]) => ({ conversationId, token }))
    });
    return response.data.conversations;
}
function authHeaders(conversationId) {
    const token = getConversationToken(conversationId);
    return token ? { "x-conversation-token": token } : {};
}
export async function uploadFiles(files) {
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));
    const response = await api.post("/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" }
    });
    return response.data;
}
export async function uploadMoreFiles(conversationId, files) {
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));
    const response = await api.post(`/conversations/${conversationId}/files`, formData, {
        headers: {
            "Content-Type": "multipart/form-data",
            ...authHeaders(conversationId)
        }
    });
    return response.data;
}
export async function getConversation(conversationId) {
    const response = await api.get(`/conversations/${conversationId}`, {
        headers: authHeaders(conversationId)
    });
    return response.data;
}
export async function askQuestion(conversationId, question) {
    const response = await api.post("/ask", { conversationId, question });
    return response.data;
}
export function getStreamUrl(conversationId, question) {
    // @ts-ignore
    const base = (import.meta.env.VITE_API_BASE_URL || "http://localhost:3000/api").replace(/\/api$/, "");
    const url = new URL(`${base}/api/stream-answer`);
    url.searchParams.set("conversationId", conversationId);
    url.searchParams.set("question", question);
    return url.toString();
}
export async function requestUploadAccess(conversationId, displayName) {
    const response = await api.post(`/conversations/${conversationId}/access-requests`, { displayName });
    return response.data;
}
export async function getUploadAccessRequest(conversationId, requestId) {
    const response = await api.get(`/conversations/${conversationId}/access-requests/${requestId}`);
    return response.data;
}
export async function approveUploadAccess(conversationId, requestId) {
    const response = await api.post(`/conversations/${conversationId}/access-requests/${requestId}/approve`, {}, { headers: authHeaders(conversationId) });
    return response.data;
}
export async function renameConversation(conversationId, displayName) {
    const response = await api.patch(`/conversations/${conversationId}/name`, { displayName }, { headers: authHeaders(conversationId) });
    return response.data;
}
