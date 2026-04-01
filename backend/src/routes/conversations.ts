import Router from "@koa/router";
import { getConversation } from "../repositories/conversations.js";

export const conversationsRouter = new Router();

conversationsRouter.get("/conversations/:conversationId", async (ctx) => {
  const conversationId = ctx.params.conversationId;
  const data = await getConversation(conversationId);

  if (!data.conversation) {
    ctx.status = 404;
    ctx.body = { error: "Conversation not found" };
    return;
  }

  ctx.body = {
    conversationId: data.conversation.id,
    status: data.conversation.status,
    files: data.files.map((file) => ({
      id: file.id,
      originalName: file.original_name,
      mimeType: file.mime_type,
      sizeBytes: Number(file.size_bytes)
    })),
    suggestedQuestions: data.suggestedQuestions.map((row) => row.question),
    errorMessage: data.conversation.error_message
  };
});
