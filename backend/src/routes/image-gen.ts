import Router from "@koa/router";
import path from "node:path";
import { z } from "zod";
import { getConversation, insertConversationMessage, resolveConversationRole } from "../repositories/conversations.js";
import { generateImage } from "../python/image-gen.js";
import { buildChatHistory, getWelcomeMessages } from "../utils/chat-history.js";
import { config } from "../config.js";

const imageGenSchema = z.object({
  conversationId: z.string().regex(/^[0-9A-Za-z]{16}$/),
  question: z.string().min(1),
  userId: z.number().int().min(0).optional(),
});

export const imageGenRouter = new Router();

imageGenRouter.post("/generate-image", async (ctx) => {
  const parsed = imageGenSchema.safeParse(ctx.request.body);
  if (!parsed.success) {
    ctx.status = 400;
    ctx.body = { error: "Invalid request" };
    return;
  }

  const { conversationId, question, userId } = parsed.data;

  const token = String(ctx.headers["x-conversation-token"] || "");
  const role = await resolveConversationRole(conversationId, token);
  if (role !== "owner" && role !== "editor") {
    ctx.status = 403;
    ctx.body = { error: "Only the conversation owner can generate images" };
    return;
  }

  const data = await getConversation(conversationId);
  if (!data.conversation) {
    ctx.status = 404;
    ctx.body = { error: "Conversation not found" };
    return;
  }

  // Insert user message (the image generation request)
  const userMsgId = await insertConversationMessage({
    conversationId,
    role: "user",
    content: question,
    userId: userId || 0,
  });

  const welcomeMessages = data.parentWelcomeContents.length
    ? data.parentWelcomeContents
    : getWelcomeMessages(data.messages);

  const chatHistory = buildChatHistory(data.messages);
  const context = chatHistory
    .slice(-6)
    .map((m) => `${m.role}: ${m.content.slice(0, 300)}`)
    .join("\n");

  const storageDir = path.join(config.storageRoot, data.conversation.storage_namespace);

  const result = await generateImage({
    question,
    storageDir,
    context,
    welcomeMessages,
  });

  // Build the assistant answer with the image
  const imageUrl = `/api/storage/${conversationId}/${result.file_name}`;
  const answer = `🎨 Here's the generated image:\n\n![Generated image](${imageUrl})\n\n_${result.image_prompt}_`;

  const assistantMsgId = await insertConversationMessage({
    conversationId,
    role: "assistant",
    content: answer,
  });

  ctx.body = {
    answer,
    citations: [],
    userMessageId: userMsgId,
    assistantMessageId: assistantMsgId,
    generatedImage: {
      fileName: result.file_name,
      imagePrompt: result.image_prompt,
      revisedPrompt: result.revised_prompt,
    },
  };
});
