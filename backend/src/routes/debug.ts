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
  if (!config.debugUser || !config.debugPass || !safeEq(user, config.debugUser) || !safeEq(pass, config.debugPass)) {
    ctx.status = 401;
    ctx.body = { error: "Invalid credentials" };
    return;
  }

  const offset = Math.max(0, parseInt(String(ctx.query.offset ?? "0"), 10) || 0);
  const limit = 1000;

  const [
    conversations,
    messages,
    suggestedQuestions,
    uploadedFiles,
    userFingerprints,
    conversationAccessTokens,
    accessRequests,
    users,
  ] = await Promise.all([
    query("SELECT * FROM public.conversations ORDER BY created_at DESC LIMIT $1 OFFSET $2", [limit, offset]),
    query("SELECT * FROM public.conversation_messages ORDER BY created_at DESC LIMIT $1 OFFSET $2", [limit, offset]),
    query("SELECT * FROM public.suggested_questions ORDER BY created_at DESC LIMIT $1 OFFSET $2", [limit, offset]),
    query("SELECT * FROM public.uploaded_files ORDER BY created_at DESC LIMIT $1 OFFSET $2", [limit, offset]),
    query("SELECT * FROM public.user_fingerprints ORDER BY created_at DESC LIMIT $1 OFFSET $2", [limit, offset]),
    query("SELECT * FROM public.conversation_access_tokens ORDER BY created_at DESC LIMIT $1 OFFSET $2", [limit, offset]),
    query("SELECT * FROM public.access_requests ORDER BY created_at DESC LIMIT $1 OFFSET $2", [limit, offset]),
    query(`SELECT cm.user_id, uf.fingerprint, COUNT(*) AS message_count,
                  MIN(cm.created_at) AS first_seen, MAX(cm.created_at) AS last_seen
           FROM public.conversation_messages cm
           LEFT JOIN public.user_fingerprints uf ON uf.user_id = cm.user_id
           GROUP BY cm.user_id, uf.fingerprint
           ORDER BY message_count DESC`),
  ]);

  ctx.body = {
    conversations: conversations.rows,
    conversation_messages: messages.rows,
    suggested_questions: suggestedQuestions.rows,
    uploaded_files: uploadedFiles.rows,
    user_fingerprints: userFingerprints.rows,
    conversation_access_tokens: conversationAccessTokens.rows,
    access_requests: accessRequests.rows,
    users: users.rows,
  };
});
