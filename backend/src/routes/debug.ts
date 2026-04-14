import Router from "@koa/router";
import { query } from "../db.js";

export const debugRouter = new Router();

debugRouter.get("/debug/tables", async (ctx) => {
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
