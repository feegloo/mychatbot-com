import Router from "@koa/router";
import { spawn } from "node:child_process";
import path from "node:path";
import { config } from "../config.js";
import { getConversation } from "../repositories/conversations.js";

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

  ctx.req.setTimeout(60_000);

  ctx.set("Content-Type", "text/event-stream");
  ctx.set("Cache-Control", "no-cache");
  ctx.set("Connection", "keep-alive");

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

  child.stdout.on("data", (chunk) => {
    const lines = chunk.toString().split("\n").filter(Boolean);
    for (const line of lines) {
      ctx.res.write(line + "\n\n");
    }
  });

  child.stderr.on("data", (chunk) => {
    const payload = JSON.stringify({ error: chunk.toString() });
    ctx.res.write(`event: error\ndata: ${payload}\n\n`);
  });

  child.on("close", () => {
    ctx.res.write(`event: done\ndata: {}\n\n`);
    ctx.res.end();
  });

  ctx.respond = false;
});
