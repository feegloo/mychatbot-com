import Router from "@koa/router";
import { getConversation, resolveConversationRole } from "../repositories/conversations.js";

export const conversationsRouter = new Router();

conversationsRouter.get("/conversations/:conversationId", async (ctx) => {
  const conversationId = ctx.params.conversationId;
  const token = String(ctx.headers["x-conversation-token"] || "");
  const role = await resolveConversationRole(conversationId, token);
  const data = await getConversation(conversationId, role);

  if (!data.conversation) {
    ctx.status = 404;
    ctx.body = { error: "Conversation not found" };
    return;
  }

  ctx.body = {
    conversationId: data.conversation.id,
    status: data.conversation.status,
    role,
    files: data.files.map((file) => ({
      id: file.id,
      originalName: file.original_name,
      mimeType: file.mime_type,
      sizeBytes: Number(file.size_bytes)
    })),
    messages: data.messages.map((message) => ({
      id: message.id,
      role: message.role,
      content: message.content,
      citations: message.citations_json || []
    })),
    suggestedQuestions: data.suggestedQuestions.map((row) => row.question),
    accessRequests: data.accessRequests.map((row) => ({
      id: row.id,
      displayName: row.display_name,
      status: row.status
    })),
    errorMessage: data.conversation.error_message
  };
});
