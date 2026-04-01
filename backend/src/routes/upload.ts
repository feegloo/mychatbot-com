import Router from "@koa/router";
import multer from "@koa/multer";
import path from "node:path";
import { v4 as uuidv4 } from "uuid";
import { createStorageProvider } from "../storage/index.js";
import { insertConversation, insertUploadedFile, replaceSuggestedQuestions, updateConversationStatus } from "../repositories/conversations.js";
import { config } from "../config.js";
import { indexConversation } from "../python/indexing.js";

const upload = multer({ storage: multer.memoryStorage() });
export const uploadRouter = new Router();

uploadRouter.post("/upload", upload.array("files"), async (ctx) => {
  const files = (ctx.files || []) as Express.Multer.File[];
  if (!files.length) {
    ctx.status = 400;
    ctx.body = { error: "No files uploaded" };
    return;
  }

  const conversationId = uuidv4();
  const namespace = conversationId;
  const collectionName = `conversation_${conversationId.replace(/-/g, "_")}`;
  const storage = createStorageProvider();

  await insertConversation({
    id: conversationId,
    status: "processing",
    storage_namespace: namespace,
    vector_collection_name: collectionName,
    indexing_mode: config.pythonIndexingMode,
    error_message: null
  });

  const absolutePaths: string[] = [];

  for (const file of files) {
    const saved = await storage.save(namespace, file.originalname, {
      originalName: file.originalname,
      mimeType: file.mimetype || "application/octet-stream",
      buffer: file.buffer
    });

    const storedName = path.basename(saved.storageKey);

    await insertUploadedFile({
      id: uuidv4(),
      conversation_id: conversationId,
      original_name: file.originalname,
      stored_name: storedName,
      mime_type: file.mimetype || "application/octet-stream",
      size_bytes: file.size,
      storage_key: saved.storageKey
    });

    if (saved.absolutePath) {
      absolutePaths.push(saved.absolutePath);
    }
  }

  indexConversation({
    conversationId,
    collectionName,
    files: absolutePaths,
    mode: (config.pythonIndexingMode === "notebook" ? "notebook" : "script")
  })
    .then(async (result) => {
      const suggestedQuestions = result.parsedJson?.suggested_questions || [];
      await replaceSuggestedQuestions(conversationId, suggestedQuestions);
      await updateConversationStatus(conversationId, "ready");
    })
    .catch(async (error) => {
      await updateConversationStatus(conversationId, "failed", error.message);
    });

  ctx.body = {
    conversationId,
    status: "processing",
    url: `/c/${conversationId}`
  };
});
