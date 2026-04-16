import Router from "@koa/router";
import path from "node:path";
import { z } from "zod";
import { getConversation, insertConversationMessage } from "../repositories/conversations.js";
import { answerQuestion } from "../python/answering.js";
import { ensureCollectionIndexed } from "../python/reindex.js";
import { buildChatHistory, getWelcomeMessages } from "../utils/chat-history.js";
import { config } from "../config.js";

const askSchema = z.object({
  conversationId: z.string().regex(/^[0-9A-Za-z]{16}$/),
  question: z.string().min(1),
  userId: z.number().int().min(0).optional()
});

export const askRouter = new Router();

askRouter.post("/ask", async (ctx) => {
  const parsed = askSchema.safeParse(ctx.request.body);
  if (!parsed.success) {
    ctx.status = 400;
    ctx.body = { error: "Invalid request" };
    return;
  }

  const { conversationId, question, userId } = parsed.data;
  const data = await getConversation(conversationId);

  if (!data.conversation) {
    ctx.status = 404;
    ctx.body = { error: "Conversation not found" };
    return;
  }

  if (data.conversation.status !== "ready") {
    ctx.status = 409;
    ctx.body = { error: "Conversation is not ready yet", status: data.conversation.status };
    return;
  }

  await insertConversationMessage({
    conversationId,
    role: "user",
    content: question,
    userId: userId || 0
  });

  // Ensure vector collection has data (re-index if Chroma was lost on container restart)
  await ensureCollectionIndexed(conversationId, data.conversation.vector_collection_name, data.conversation.storage_namespace);

  const chatHistory = buildChatHistory(data.messages);
  // For threads, use parent's welcome messages (file descriptions) as context;
  // for normal conversations, extract from the conversation's own messages.
  const welcomeMessages = data.parentWelcomeContents.length
    ? data.parentWelcomeContents
    : getWelcomeMessages(data.messages);

  // Resolve image file paths and metadata for Vision API (used on "recognize person name")
  const IMAGE_EXTS = new Set([".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif"]);
  const imageFilePaths = data.files
    .filter(f => IMAGE_EXTS.has(path.extname(f.original_name).toLowerCase()))
    .map(f => path.join(config.storageRoot, f.storage_key));
  const fileMetadata: Record<string, any> = {};
  for (const f of data.files) {
    if (f.metadata_json) fileMetadata[f.original_name] = f.metadata_json;
  }

  const result = await answerQuestion({
    conversationId,
    collectionName: data.conversation.vector_collection_name,
    question,
    chatHistory,
    welcomeMessages,
    imageFilePaths: imageFilePaths.length ? imageFilePaths : undefined,
    fileMetadata: Object.keys(fileMetadata).length ? fileMetadata : undefined,
  });

  const payload = result.parsedJson || {
    answer: result.stdout,
    citations: []
  };

  await insertConversationMessage({
    conversationId,
    role: "assistant",
    content: payload.answer || "",
    citations: payload.citations || []
  });

  ctx.body = payload;
});
