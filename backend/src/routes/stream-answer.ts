import Router from "@koa/router";
import { config } from "../config.js";
import { getConversation, insertConversationMessage } from "../repositories/conversations.js";
import { ensureCollectionIndexed } from "../python/reindex.js";
import { buildChatHistory } from "../utils/chat-history.js";

export const streamAnswerRouter = new Router();

streamAnswerRouter.get("/stream-answer", async (ctx) => {
  const conversationId = String(ctx.query.conversationId || "");
  const question = String(ctx.query.question || "");

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
    content: question
  });

  // Ensure vector collection has data (re-index if Chroma was lost on container restart)
  await ensureCollectionIndexed(conversationId, data.conversation.vector_collection_name);

  // Build chat history from the last Q&A exchange (last user + assistant messages)
  const chatHistory = buildChatHistory(data.messages);

  ctx.req.setTimeout(60_000);

  ctx.set("Content-Type", "text/event-stream");
  ctx.set("Cache-Control", "no-cache");
  ctx.set("Connection", "keep-alive");

  console.log("[stream-answer] starting", {
    conversationId,
    questionLength: question.length
  });

  let assistantText = "";
  let citations: unknown[] = [];

  try {
    const response = await fetch(`${config.pythonServerUrl}/stream-answer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: conversationId,
        collection_name: data.conversation.vector_collection_name,
        question,
        chat_history: chatHistory,
      }),
    });

    if (!response.ok || !response.body) {
      const text = await response.text();
      ctx.res.write(`event: error\ndata: ${JSON.stringify({ error: text })}\n\n`);
      ctx.res.write(`event: done\ndata: {}\n\n`);
      ctx.res.end();
      ctx.respond = false;
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    let currentEvent = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      const lines = chunk.split("\n").filter(Boolean);

      for (const line of lines) {
        if (line.startsWith("event: ")) {
          currentEvent = line.replace("event: ", "").trim();
        }
        if (line.startsWith("data: ")) {
          const dataStr = line.replace("data: ", "");
          try {
            const payload = JSON.parse(dataStr);
            if (currentEvent === "token" && payload.token) assistantText += payload.token;
            if (currentEvent === "citations" && Array.isArray(payload.citations)) citations = payload.citations;
          } catch {}
        }
        ctx.res.write(line + "\n");
      }
      ctx.res.write("\n");
    }
  } catch (err: any) {
    console.error("[stream-answer] error", err);
    ctx.res.write(`event: error\ndata: ${JSON.stringify({ error: err.message })}\n\n`);
  }

  console.log("[stream-answer] finished", { conversationId });

  if (assistantText.trim()) {
    await insertConversationMessage({
      conversationId,
      role: "assistant",
      content: assistantText,
      citations
    });
  }

  ctx.res.write(`event: done\ndata: {}\n\n`);
  ctx.res.end();
  ctx.respond = false;
});
