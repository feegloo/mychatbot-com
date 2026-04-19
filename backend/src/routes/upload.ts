import Router from "@koa/router";
import multer from "@koa/multer";
import path from "node:path";
import { v4 as uuidv4 } from "uuid";
import * as Sentry from "@sentry/node";
import { generateShortId } from "../utils/id.js";
import { createStorageProvider } from "../storage/index.js";
import { insertConversation, insertUploadedFile, replaceSuggestedQuestions, updateConversationStatus, insertAccessToken, insertConversationMessage, updateFileMetadata, resolveConversationRole } from "../repositories/conversations.js";
import { config } from "../config.js";
import { indexConversation, describeUrl } from "../python/indexing.js";
import { deriveToken } from "../security.js";
import { generateSignedUploadUrl, downloadGcsFileToLocal } from "../storage/gcs-storage.js";

const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 100 * 1024 * 1024 } });
export const uploadRouter = new Router();

uploadRouter.post("/upload", upload.array("files"), async (ctx) => {
  const files = ctx.files as multer.File[] || [];
  if (!files.length) {
    ctx.status = 400;
    ctx.body = { error: "No files uploaded" };
    return;
  }

  const videoFiles = files.filter(f => f.mimetype?.startsWith("video/"));
  if (videoFiles.length) {
    ctx.status = 400;
    ctx.body = { error: "Video files are not supported." };
    return;
  }

  const conversationId = generateShortId();
  const salt = uuidv4();
  const ownerPassword = deriveToken(conversationId, salt);
  const namespace = conversationId;
  const collectionName = `conversation_${conversationId}`;
  const storage = createStorageProvider();

  await insertConversation({
    id: conversationId,
    salt: salt,
    display_name: null,
    status: "processing",
    storage_namespace: namespace,
    vector_collection_name: collectionName,
    indexing_mode: config.pythonIndexingMode,
    error_message: null,
    parent_message_id: null,
    parent_conversation_id: null
  });

  // Create owner access token - use derived token
  await insertAccessToken({
    token: ownerPassword,
    conversation_id: conversationId,
    role: "owner"
  });

  const absolutePaths: string[] = [];
  const uploadedFileNames: string[] = [];
  const storedToOriginal: Record<string, string> = {};

  for (const file of files) {
    const originalName = Buffer.from(file.originalname, "latin1").toString("utf8").normalize("NFC");
    const saved = await storage.save(namespace, originalName, {
      originalName,
      mimeType: file.mimetype || "application/octet-stream",
      buffer: file.buffer
    });

    const storedName = path.basename(saved.storageKey);

    await insertUploadedFile({
      id: uuidv4(),
      conversation_id: conversationId,
      original_name: originalName,
      stored_name: storedName,
      mime_type: file.mimetype || "application/octet-stream",
      size_bytes: file.size,
      storage_key: saved.storageKey
    });

    uploadedFileNames.push(originalName);
    storedToOriginal[storedName] = originalName;
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
      Sentry.logger.info(Sentry.logger.fmt`Indexing completed for conversation ${conversationId}`, {
        conversation_id: conversationId,
        file_count: files.length,
        suggested_questions_count: (result.parsedJson?.suggested_questions || []).length,
        has_welcome_message: !!(result.parsedJson?.welcome_message),
      });
      const suggestedQuestions = result.parsedJson?.suggested_questions || [];
      const welcomeMessage = result.parsedJson?.welcome_message || "";
      const fileMetadata = result.parsedJson?.file_metadata || {};
      const fallbackMessage = welcomeMessage
        || `## ${uploadedFileNames.join(", ")}\n\nFile uploaded and ready. Ask me anything about ${uploadedFileNames.length === 1 ? "this document" : "these documents"}.`;
      const messageId = await insertConversationMessage({
        conversationId,
        role: "assistant",
        content: fallbackMessage,
        citations: { _uploadedFileNames: uploadedFileNames },
      });
      // Store file metadata per file
      for (const [fileName, metadata] of Object.entries(fileMetadata)) {
        try {
          const origName = storedToOriginal[fileName] || fileName;
          await updateFileMetadata(conversationId, origName, metadata);
        } catch (err: any) {
          console.error(`[metadata update error for ${fileName}]:`, err.message);
        }
      }
      await replaceSuggestedQuestions(conversationId, suggestedQuestions, messageId);
      await updateConversationStatus(conversationId, "ready");
    })
    .catch(async (error) => {
      await updateConversationStatus(conversationId, "failed", error.message);
    });

  ctx.body = {
    conversationId,
    status: "processing",
    url: `/c/${conversationId}`,
    ownerPassword
  };
});

// ── Direct-to-GCS upload for large files (bypasses Cloud Run 32 MiB proxy limit) ──

uploadRouter.post("/upload/signed-url", async (ctx) => {
  if (config.storageProvider !== "gcs") {
    ctx.status = 400;
    ctx.body = { error: "Direct upload only available with GCS storage" };
    return;
  }

  const { files } = ctx.request.body as { files?: Array<{ name: string; mimeType: string; size: number }> };
  if (!files?.length) {
    ctx.status = 400;
    ctx.body = { error: "No files specified" };
    return;
  }

  if (files.length > 20) {
    ctx.status = 400;
    ctx.body = { error: "Maximum 20 files per upload" };
    return;
  }

  const videoFiles = files.filter(f => f.mimeType?.startsWith("video/"));
  if (videoFiles.length) {
    ctx.status = 400;
    ctx.body = { error: "Video files are not supported." };
    return;
  }

  const conversationId = generateShortId();
  const salt = uuidv4();
  const ownerPassword = deriveToken(conversationId, salt);
  const namespace = conversationId;
  const collectionName = `conversation_${conversationId}`;

  await insertConversation({
    id: conversationId,
    salt,
    display_name: null,
    status: "uploading",
    storage_namespace: namespace,
    vector_collection_name: collectionName,
    indexing_mode: config.pythonIndexingMode,
    error_message: null,
    parent_message_id: null,
    parent_conversation_id: null,
  });

  await insertAccessToken({
    token: ownerPassword,
    conversation_id: conversationId,
    role: "owner",
  });

  const signedUrls: Array<{ name: string; signedUrl: string; gcsKey: string; storedName: string }> = [];

  for (const file of files) {
    const originalName = file.name.normalize("NFC");
    const mimeType = file.mimeType || "application/octet-stream";
    const { gcsKey, storedName, signedUrl } = await generateSignedUploadUrl(namespace, originalName, mimeType);
    signedUrls.push({ name: originalName, signedUrl, gcsKey, storedName });
  }

  ctx.body = {
    conversationId,
    ownerPassword,
    url: `/c/${conversationId}`,
    signedUrls,
  };
});

uploadRouter.post("/upload/finalize", async (ctx) => {
  const { conversationId, files: fileEntries } = ctx.request.body as {
    conversationId?: string;
    files?: Array<{ name: string; mimeType: string; size: number; gcsKey: string; storedName: string }>;
  };

  if (!conversationId || !fileEntries?.length) {
    ctx.status = 400;
    ctx.body = { error: "Missing conversationId or files" };
    return;
  }

  const token = String(ctx.headers["x-conversation-token"] || "");
  if (!token) {
    ctx.status = 401;
    ctx.body = { error: "Missing auth token" };
    return;
  }

  const role = await resolveConversationRole(conversationId, token);
  if (role !== "owner") {
    ctx.status = 403;
    ctx.body = { error: "Only the owner can finalize uploads" };
    return;
  }

  await updateConversationStatus(conversationId, "processing");

  const absolutePaths: string[] = [];
  const uploadedFileNames: string[] = [];
  const storedToOriginal: Record<string, string> = {};
  const namespace = conversationId;

  for (const entry of fileEntries) {
    const originalName = entry.name.normalize("NFC");
    const storedName = entry.storedName;

    // Validate gcsKey belongs to this conversation's namespace (prevent path traversal)
    const expectedPrefix = `${namespace}/`;
    if (!entry.gcsKey.startsWith(expectedPrefix) || entry.gcsKey.includes("..")) {
      ctx.status = 400;
      ctx.body = { error: "Invalid file reference" };
      return;
    }

    // Download from GCS to local disk for Python indexing
    const absolutePath = await downloadGcsFileToLocal(entry.gcsKey, namespace);

    await insertUploadedFile({
      id: uuidv4(),
      conversation_id: conversationId,
      original_name: originalName,
      stored_name: storedName,
      mime_type: entry.mimeType || "application/octet-stream",
      size_bytes: entry.size,
      storage_key: entry.gcsKey,
    });

    uploadedFileNames.push(originalName);
    storedToOriginal[storedName] = originalName;
    absolutePaths.push(absolutePath);
  }

  const collectionName = `conversation_${conversationId}`;

  indexConversation({
    conversationId,
    collectionName,
    files: absolutePaths,
    mode: config.pythonIndexingMode === "notebook" ? "notebook" : "script",
  })
    .then(async (result) => {
      const suggestedQuestions = result.parsedJson?.suggested_questions || [];
      const welcomeMessage = result.parsedJson?.welcome_message || "";
      const fileMetadata = result.parsedJson?.file_metadata || {};
      const fallbackMessage = welcomeMessage
        || `## ${uploadedFileNames.join(", ")}\n\nFile uploaded and ready. Ask me anything about ${uploadedFileNames.length === 1 ? "this document" : "these documents"}.`;
      const messageId = await insertConversationMessage({
        conversationId,
        role: "assistant",
        content: fallbackMessage,
        citations: { _uploadedFileNames: uploadedFileNames },
      });
      for (const [fileName, metadata] of Object.entries(fileMetadata)) {
        try {
          const origName = storedToOriginal[fileName] || fileName;
          await updateFileMetadata(conversationId, origName, metadata);
        } catch (err: any) {
          console.error(`[metadata update error for ${fileName}]:`, err.message);
        }
      }
      await replaceSuggestedQuestions(conversationId, suggestedQuestions, messageId);
      await updateConversationStatus(conversationId, "ready");
    })
    .catch(async (error) => {
      await updateConversationStatus(conversationId, "failed", error.message);
    });

  ctx.body = {
    conversationId,
    status: "processing",
    url: `/c/${conversationId}`,
  };
});

uploadRouter.post("/upload-url", async (ctx) => {
  const { url } = ctx.request.body as { url?: string };
  if (!url || typeof url !== "string") {
    ctx.status = 400;
    ctx.body = { error: "No URL provided" };
    return;
  }

  // Basic URL validation
  let parsed: URL;
  try {
    parsed = new URL(url);
    if (!["http:", "https:"].includes(parsed.protocol)) {
      throw new Error("Invalid protocol");
    }
  } catch {
    ctx.status = 400;
    ctx.body = { error: "Invalid URL" };
    return;
  }

  const conversationId = generateShortId();
  const salt = uuidv4();
  const ownerPassword = deriveToken(conversationId, salt);
  const namespace = conversationId;
  const collectionName = `conversation_${conversationId}`;

  await insertConversation({
    id: conversationId,
    salt: salt,
    display_name: null,
    status: "processing",
    storage_namespace: namespace,
    vector_collection_name: collectionName,
    indexing_mode: config.pythonIndexingMode,
    error_message: null,
    parent_message_id: null,
    parent_conversation_id: null
  });

  await insertAccessToken({
    token: ownerPassword,
    conversation_id: conversationId,
    role: "owner"
  });

  describeUrl({
    url,
    conversationId,
    collectionName,
  })
    .then(async (result) => {
      const suggestedQuestions = result.parsedJson?.suggested_questions || [];
      const welcomeMessage = result.parsedJson?.welcome_message || "";
      const fallbackMessage = welcomeMessage
        || `## ${parsed.hostname}\n\nWebsite loaded and ready. Ask me anything about this page.`;
      const messageId = await insertConversationMessage({
        conversationId,
        role: "assistant",
        content: fallbackMessage,
        citations: { _sourceUrl: url },
      });
      await replaceSuggestedQuestions(conversationId, suggestedQuestions, messageId);
      await updateConversationStatus(conversationId, "ready");
    })
    .catch(async (error) => {
      await updateConversationStatus(conversationId, "failed", error.message);
    });

  ctx.body = {
    conversationId,
    status: "processing",
    url: `/c/${conversationId}`,
    ownerPassword
  };
});
