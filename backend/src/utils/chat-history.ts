import type { ConversationMessageRecord } from "../types.js";

/**
 * Extract the last user+assistant exchange from conversation messages
 * to provide as chat history context. Only includes the most recent
 * Q&A pair to avoid blowing up the context window.
 */
export function buildChatHistory(messages: ConversationMessageRecord[]): { role: string; content: string }[] {
  // Find the last assistant message and the user message before it
  const history: { role: string; content: string }[] = [];

  // Walk backwards to find the last assistant message
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "assistant") {
      // Found the last assistant message — now find the user message before it
      for (let j = i - 1; j >= 0; j--) {
        if (messages[j].role === "user") {
          history.push({ role: "user", content: messages[j].content });
          break;
        }
      }
      history.push({ role: "assistant", content: messages[i].content });
      break;
    }
  }

  return history;
}
