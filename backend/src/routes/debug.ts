import Router from "@koa/router";
import { timingSafeEqual } from "node:crypto";
import { query } from "../db.js";
import { config } from "../config.js";

function safeEq(a: string, b: string): boolean {
  const bufA = Buffer.from(a);
  const bufB = Buffer.from(b);
  if (bufA.length !== bufB.length) return false;
  return timingSafeEqual(bufA, bufB);
}

export const debugRouter = new Router();

debugRouter.get("/debug/tables", async (ctx) => {
  const auth = ctx.headers.authorization;
  if (!auth || !auth.startsWith("Basic ")) {
    ctx.status = 401;
    ctx.body = { error: "Authentication required" };
    return;
  }
  const decoded = Buffer.from(auth.slice(6), "base64").toString();
  const idx = decoded.indexOf(":");
  const user = idx < 0 ? decoded : decoded.slice(0, idx);
  const pass = idx < 0 ? "" : decoded.slice(idx + 1);
  if (!safeEq(user, config.debugUser) || !safeEq(pass, config.debugPass)) {
    ctx.status = 401;
    ctx.body = { error: "Invalid credentials" };
    return;
  }

  const [conversations, messages, suggestedQuestions, uploadedFiles] =
    await Promise.all([
      query("SELECT * FROM public.conversations ORDER BY created_at DESC LIMIT 1000"),
      query("SELECT * FROM public.conversation_messages ORDER BY created_at DESC LIMIT 1000"),
      query("SELECT * FROM public.suggested_questions LIMIT 1000"),
      query("SELECT * FROM public.uploaded_files LIMIT 1000"),
    ]);

  ctx.body = {
    conversations: conversations.rows,
    conversation_messages: messages.rows,
    suggested_questions: suggestedQuestions.rows,
    uploaded_files: uploadedFiles.rows,
  };
});
