import Router from "@koa/router";
import { z } from "zod";
import { getConversation } from "../repositories/conversations.js";
import { answerQuestion } from "../python/answering.js";

const askSchema = z.object({
  conversationId: z.string().uuid(),
  question: z.string().min(3)
});

export const askRouter = new Router();

askRouter.post("/ask", async (ctx) => {
  const parsed = askSchema.safeParse(ctx.request.body);
  if (!parsed.success) {
    ctx.status = 400;
    ctx.body = { error: "Invalid request" };
    return;
  }

  const { conversationId, question } = parsed.data;
  const data = await getConversation(conversationId);

  if (!data.conversation) {
    ctx.status = 404;
    ctx.body = { error: "Conversation not found" };
    return;
  }

  if (data.conversation.status !== "ready") {
    ctx.status = 409;
    ctx.body = { error: "Conversation is not ready yet" };
    return;
  }

  const result = await answerQuestion({
    conversationId,
    collectionName: data.conversation.vector_collection_name,
    question
  });

  ctx.body = result.parsedJson || {
    answer: result.stdout,
    citations: []
  };
});
