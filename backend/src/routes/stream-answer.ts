import Router from "@koa/router";
import { spawn } from "node:child_process";
import path from "node:path";
import { config } from "../config.js";
import { getConversation, insertConversationMessage } from "../repositories/conversations.js";

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

  ctx.req.setTimeout(60_000);

  ctx.set("Content-Type", "text/event-stream");
  ctx.set("Cache-Control", "no-cache");
  ctx.set("Connection", "keep-alive");

  console.log("[stream-answer] starting", {
    conversationId,
    questionLength: question.length
  });

  const child = spawn(config.pythonBin, [
    path.join(config.pythonProjectRoot, "stream_answer.py"),
    "--conversation-id", conversationId,
    "--collection-name", data.conversation.vector_collection_name,
    "--question", question
  ], {
    cwd: config.pythonProjectRoot,
    env: {
      ...process.env,
      OPENAI_API_KEY: config.openAiApiKey,
      OPENAI_CHAT_MODEL: config.openAiChatModel,
      OPENAI_EMBEDDING_MODEL: config.openAiEmbeddingModel,
      CHROMA_MODE: config.chromaMode,
      CHROMA_HTTP_HOST: config.chromaHttpHost,
      CHROMA_PERSIST_DIR: config.chromaPersistDir
    }
  });

  let assistantText = "";
  let citations: unknown[] = [];

  child.stdout.on("data", (chunk) => {
    const lines = chunk.toString().split("\n").filter(Boolean);
    let currentEvent = "";
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
  });

  child.stderr.on("data", (chunk) => {
    const text = chunk.toString();
    console.error("[python:stream-answer:stderr]", text);
    const payload = JSON.stringify({ error: text });
    ctx.res.write(`event: error\ndata: ${payload}\n\n`);
  });

  child.on("close", async () => {
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
  });

  ctx.respond = false;
});
