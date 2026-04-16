import Router from "@koa/router";
import multer from "@koa/multer";
import path from "node:path";
import { z } from "zod";
import { v4 as uuidv4 } from "uuid";
import { getConversation, resolveConversationRole, insertUploadedFile, updateConversationStatus, replaceSuggestedQuestions, appendSuggestedQuestions, createAccessRequest, getAccessRequest, approveAccessRequest, insertAccessToken, insertConversation, updateConversationDisplayName, getConversationSummaries, insertConversationMessage, getMessageById, updateFileMetadata, resolveUserByFingerprint, getThreadsForMessage, getThreadReplyCountsForMessages } from "../repositories/conversations.js";
import { createStorageProvider } from "../storage/index.js";
import { generateShortId } from "../utils/id.js";
import { config } from "../config.js";
import { indexConversation } from "../python/indexing.js";
import { deriveToken } from "../security.js";

const upload = multer({ storage: multer.memoryStorage() });
export const conversationsRouter = new Router();

// POST /conversations — create an empty conversation (no files required)
conversationsRouter.post("/conversations", async (ctx) => {
  const conversationId = generateShortId();
  const salt = uuidv4();
  const ownerPassword = deriveToken(conversationId, salt);
  const namespace = conversationId;
  const collectionName = `conversation_${conversationId}`;

  await insertConversation({
    id: conversationId,
    salt,
    display_name: null,
    status: "ready",
    storage_namespace: namespace,
    vector_collection_name: collectionName,
    indexing_mode: config.pythonIndexingMode,
    error_message: null,
    parent_message_id: null,
  });

  await insertAccessToken({
    token: ownerPassword,
    conversation_id: conversationId,
    role: "owner",
  });

  ctx.body = {
    conversationId,
    status: "ready",
    url: `/c/${conversationId}`,
    ownerPassword,
  };
});

conversationsRouter.get("/conversations/:conversationId", async (ctx) => {
  const conversationId = ctx.params.conversationId;
  const token = String(ctx.headers["x-conversation-token"] || "");
  const role = await resolveConversationRole(conversationId, token);
  const data = await getConversation(conversationId, role);

  if (!data.conversation) {
    ctx.status = 404;
    ctx.body = { error: "Conversation not found" };
    return;
  }

  // Gather thread reply counts for all assistant messages
  const assistantMessageIds = data.messages
    .filter((m) => m.role === "assistant" && m.id)
    .map((m) => m.id);
  const threadCounts = await getThreadReplyCountsForMessages(assistantMessageIds);

  // For threads, storageNamespace differs from conversationId (points to parent's directory)
  const storageNamespace = data.conversation.storage_namespace !== data.conversation.id
    ? data.conversation.storage_namespace
    : undefined;

  ctx.body = {
    conversationId: data.conversation.id,
    displayName: data.conversation.display_name || null,
    status: data.conversation.status,
    role,
    parentMessageId: data.conversation.parent_message_id || null,
    ...(storageNamespace ? { storageNamespace } : {}),
    files: data.files.map((file) => ({
      id: file.id,
      originalName: file.original_name,
      mimeType: file.mime_type,
      sizeBytes: Number(file.size_bytes),
      metadata: file.metadata_json || null,
    })),
    messages: data.messages.map((message) => {
      const raw = message.citations_json;
      const uploadedFileNames = raw && !Array.isArray(raw) ? raw._uploadedFileNames : undefined;
      const citations = Array.isArray(raw) ? raw : [];
      // Attach per-message suggested questions
      const msgQuestions = data.suggestedQuestions
        .filter((q) => q.message_id === message.id)
        .map((q) => q.question);
      const threadReplyCount = threadCounts.get(message.id) || 0;
      // Mark the parent message (branched-from) in thread conversations
      const isParentMessage = data.conversation!.parent_message_id === message.id
        && message.conversation_id !== data.conversation!.id;
      return {
        id: message.id,
        role: message.role,
        content: message.content,
        citations,
        userId: message.user_id,
        ...(uploadedFileNames ? { uploadedFileNames } : {}),
        ...(msgQuestions.length ? { suggestedQuestions: msgQuestions } : {}),
        ...(threadReplyCount > 0 ? { threadReplyCount } : {}),
        ...(isParentMessage ? { isParentMessage: true } : {}),
      };
    }),
    suggestedQuestions: data.suggestedQuestions.map((row) => row.question),
    accessRequests: data.accessRequests.map((row) => ({
      id: row.id,
      displayName: row.display_name,
      status: row.status
    })),
    errorMessage: data.conversation.error_message
  };
});

conversationsRouter.post("/conversations/:conversationId/files", upload.array("files"), async (ctx) => {
  const conversationId = ctx.params.conversationId;
  const token = String(ctx.headers["x-conversation-token"] || "");
  const role = await resolveConversationRole(conversationId, token);
  const files = ctx.files as multer.File[] || [];

  if (!files.length) {
    ctx.status = 400;
    ctx.body = { error: "No files uploaded" };
    return;
  }

  if (role !== "owner" && role !== "editor") {
    ctx.status = 403;
    ctx.body = { error: "You don't have permission to upload files" };
    return;
  }

  const data = await getConversation(conversationId, role);

  if (!data.conversation) {
    ctx.status = 404;
    ctx.body = { error: "Conversation not found" };
    return;
  }

  const storage = createStorageProvider();
  const namespace = data.conversation.storage_namespace;
  const absolutePaths: string[] = [];
  const uploadedFileNames: string[] = [];
  const storedToOriginal: Record<string, string> = {};

  const existingNames = new Set(data.files.map((f) => f.original_name));
  const duplicates: string[] = [];

  for (const file of files) {
    const originalName = Buffer.from(file.originalname, "latin1").toString("utf8").normalize("NFC");

    if (existingNames.has(originalName)) {
      duplicates.push(originalName);
      continue;
    }
    existingNames.add(originalName);

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

  if (!absolutePaths.length) {
    ctx.status = 409;
    ctx.body = { error: "File already uploaded", duplicates };
    return;
  }

  // Set status to processing while indexing
  await updateConversationStatus(conversationId, "processing");

  indexConversation({
    conversationId,
    collectionName: data.conversation.vector_collection_name,
    files: absolutePaths,
    mode: (config.pythonIndexingMode === "notebook" ? "notebook" : "script")
  })
    .then(async (result) => {
      const suggestedQuestions = result.parsedJson?.suggested_questions || [];
      const welcomeMessage = result.parsedJson?.welcome_message || "";
      const fileMetadata = result.parsedJson?.file_metadata || {};
      let messageId: string | undefined;
      if (welcomeMessage) {
        messageId = await insertConversationMessage({
          conversationId,
          role: "assistant",
          content: welcomeMessage,
          citations: { _uploadedFileNames: uploadedFileNames },
        });
      }
      // Store file metadata per file
      for (const [fileName, metadata] of Object.entries(fileMetadata)) {
        try {
          const origName = storedToOriginal[fileName] || fileName;
          await updateFileMetadata(conversationId, origName, metadata);
        } catch (err: any) {
          console.error(`[metadata update error for ${fileName}]:`, err.message);
        }
      }
      await appendSuggestedQuestions(conversationId, suggestedQuestions, messageId);
      await updateConversationStatus(conversationId, "ready");
    })
    .catch(async (error) => {
      console.error(`[indexing error for ${conversationId}]:`, error.message);
      await updateConversationStatus(conversationId, "failed", error.message);
    });

  ctx.body = {
    conversationId,
    status: "processing",
    ...(duplicates.length ? { duplicates } : {})
  };
});

// POST /conversations/:conversationId/access-requests
// Viewer requests access to upload files
const requestAccessSchema = z.object({
  displayName: z.string().min(1)
});

conversationsRouter.post("/conversations/:conversationId/access-requests", async (ctx) => {
  const conversationId = ctx.params.conversationId;
  const parsed = requestAccessSchema.safeParse(ctx.request.body);

  if (!parsed.success) {
    ctx.status = 400;
    ctx.body = { error: "Invalid request" };
    return;
  }

  const { displayName } = parsed.data;

  try {
    const data = await getConversation(conversationId);
    if (!data.conversation) {
      ctx.status = 404;
      ctx.body = { error: "Conversation not found" };
      return;
    }

    const requestId = uuidv4();
    await createAccessRequest({
      id: requestId,
      conversation_id: conversationId,
      display_name: displayName,
      status: "pending",
      editor_token: null
    });

    ctx.body = { requestId, status: "pending" };
  } catch (err: any) {
    console.error("[access-request error]:", err.message);
    ctx.status = 500;
    ctx.body = { error: "Failed to create access request" };
  }
});

// GET /conversations/:conversationId/access-requests/:requestId
// Check if access request was approved
conversationsRouter.get("/conversations/:conversationId/access-requests/:requestId", async (ctx) => {
  const conversationId = ctx.params.conversationId;
  const requestId = ctx.params.requestId;

  try {
    const request = await getAccessRequest(conversationId, requestId);

    if (!request) {
      ctx.status = 404;
      ctx.body = { error: "Access request not found" };
      return;
    }

    ctx.body = {
      requestId: request.id,
      status: request.status,
      editorPassword: request.editor_token || null
    };
  } catch (err: any) {
    console.error("[get-access-request error]:", err.message);
    ctx.status = 500;
    ctx.body = { error: "Failed to get access request" };
  }
});

// POST /conversations/:conversationId/access-requests/:requestId/approve
// Owner approves access request
conversationsRouter.post("/conversations/:conversationId/access-requests/:requestId/approve", async (ctx) => {
  const conversationId = ctx.params.conversationId;
  const requestId = ctx.params.requestId;
  const token = String(ctx.headers["x-conversation-token"] || "");
  const role = await resolveConversationRole(conversationId, token);

  if (role !== "owner") {
    ctx.status = 403;
    ctx.body = { error: "Only owner can approve access requests" };
    return;
  }

  try {
    const request = await getAccessRequest(conversationId, requestId);

    if (!request) {
      ctx.status = 404;
      ctx.body = { error: "Access request not found" };
      return;
    }

    if (request.status !== "pending") {
      ctx.status = 400;
      ctx.body = { error: `Cannot approve ${request.status} request` };
      return;
    }

    // Get conversation to extract salt for deriving editor password
    const conv = await getConversation(conversationId, "viewer");
    if (!conv.conversation) {
      ctx.status = 404;
      ctx.body = { error: "Conversation not found" };
      return;
    }

    // Derive editor password from conversationId + salt + "editor" suffix
    const editorPassword = deriveToken(conversationId, `${conv.conversation.salt}:editor`);

    // Create access token for the requester with derived password
    await insertAccessToken({
      token: editorPassword,
      conversation_id: conversationId,
      role: "editor"
    });

    // Mark request as approved with the password
    await approveAccessRequest(conversationId, requestId, editorPassword);

    ctx.body = { requestId, status: "approved", editorPassword };
  } catch (err: any) {
    console.error("[approve-access-request error]:", err.message);
    ctx.status = 500;
    ctx.body = { error: "Failed to approve access request" };
  }
});

// PATCH /conversations/:conversationId/name
const renameSchema = z.object({
  displayName: z.string().min(1).max(200)
});

conversationsRouter.patch("/conversations/:conversationId/name", async (ctx) => {
  const conversationId = ctx.params.conversationId;
  const token = String(ctx.headers["x-conversation-token"] || "");
  const role = await resolveConversationRole(conversationId, token);

  if (role !== "owner" && role !== "editor") {
    ctx.status = 403;
    ctx.body = { error: "Only owner or editor can rename conversations" };
    return;
  }

  const parsed = renameSchema.safeParse(ctx.request.body);
  if (!parsed.success) {
    ctx.status = 400;
    ctx.body = { error: "Invalid display name" };
    return;
  }

  await updateConversationDisplayName(conversationId, parsed.data.displayName);
  ctx.body = { displayName: parsed.data.displayName };
});

const batchSchema = z.object({
  conversations: z.array(z.object({
    conversationId: z.string().regex(/^[0-9A-Za-z-]{16,36}$/),
    token: z.string()
  })).max(100)
});

conversationsRouter.post("/conversations/batch", async (ctx) => {
  const parsed = batchSchema.safeParse(ctx.request.body);
  if (!parsed.success) {
    ctx.status = 400;
    ctx.body = { error: "Invalid request body" };
    return;
  }

  const ids = parsed.data.conversations.map((c) => c.conversationId);
  const summaries = await getConversationSummaries(ids);

  const results = await Promise.all(
    summaries.map(async (row) => {
      const entry = parsed.data.conversations.find((c) => c.conversationId === row.id);
      const role = await resolveConversationRole(row.id, entry?.token);
      return {
        conversationId: row.id,
        displayName: row.display_name || null,
        status: row.status,
        role,
        fileNames: row.fileNames
      };
    })
  );

  ctx.body = { conversations: results };
});

conversationsRouter.get("/messages/:messageId", async (ctx) => {
  const messageId = ctx.params.messageId;
  if (!/^[0-9A-Za-z]{16}$/.test(messageId)) {
    ctx.status = 400;
    ctx.body = { error: "Invalid message ID" };
    return;
  }

  const msg = await getMessageById(messageId);
  if (!msg || msg.role !== "assistant") {
    ctx.status = 404;
    ctx.body = { error: "Message not found" };
    return;
  }

  const citations = Array.isArray(msg.citations_json) ? msg.citations_json : [];
  ctx.body = {
    id: msg.id,
    conversationId: msg.conversation_id,
    displayName: msg.display_name || null,
    role: msg.role,
    content: msg.content,
    citations,
  };
});

// POST /fingerprint — resolve browser fingerprint to userId
const fingerprintSchema = z.object({
  fingerprint: z.string().min(8).max(128)
});

conversationsRouter.post("/fingerprint", async (ctx) => {
  const parsed = fingerprintSchema.safeParse(ctx.request.body);
  if (!parsed.success) {
    ctx.status = 400;
    ctx.body = { error: "Invalid fingerprint" };
    return;
  }
  const userId = await resolveUserByFingerprint(parsed.data.fingerprint);
  ctx.body = { userId };
});

// GET /messages/:messageId/threads — get all thread conversations for a shared message
conversationsRouter.get("/messages/:messageId/threads", async (ctx) => {
  const messageId = ctx.params.messageId;
  if (!/^[0-9A-Za-z]{16}$/.test(messageId)) {
    ctx.status = 400;
    ctx.body = { error: "Invalid message ID" };
    return;
  }

  const threads = await getThreadsForMessage(messageId);
  ctx.body = {
    threads: threads.map((t) => ({
      conversationId: t.id,
      displayName: t.display_name,
      messageCount: (t as any).message_count || 0,
      lastUserId: (t as any).last_user_id || 0,
    })),
  };
});

// POST /messages/:messageId/threads — create a new thread conversation from a shared message
const createThreadSchema = z.object({
  userId: z.number().int().min(1)
});

conversationsRouter.post("/messages/:messageId/threads", async (ctx) => {
  const messageId = ctx.params.messageId;
  if (!/^[0-9A-Za-z]{16}$/.test(messageId)) {
    ctx.status = 400;
    ctx.body = { error: "Invalid message ID" };
    return;
  }

  const parsed = createThreadSchema.safeParse(ctx.request.body);
  if (!parsed.success) {
    ctx.status = 400;
    ctx.body = { error: "Invalid request" };
    return;
  }

  // Verify parent message exists
  const parentMsg = await getMessageById(messageId);
  if (!parentMsg) {
    ctx.status = 404;
    ctx.body = { error: "Parent message not found" };
    return;
  }

  // Get the parent conversation to copy its vector collection for RAG
  const parentConv = await getConversation(parentMsg.conversation_id);
  if (!parentConv.conversation) {
    ctx.status = 404;
    ctx.body = { error: "Parent conversation not found" };
    return;
  }

  // Create thread conversation
  const threadId = generateShortId();
  const salt = uuidv4();
  const ownerPassword = deriveToken(threadId, salt);

  await insertConversation({
    id: threadId,
    salt,
    display_name: null,
    status: "ready",
    storage_namespace: parentConv.conversation.storage_namespace,
    vector_collection_name: parentConv.conversation.vector_collection_name,
    indexing_mode: parentConv.conversation.indexing_mode,
    error_message: null,
    parent_message_id: messageId,
  });

  await insertAccessToken({
    token: ownerPassword,
    conversation_id: threadId,
    role: "owner",
  });

  ctx.body = {
    conversationId: threadId,
    ownerPassword,
    url: `/c/${threadId}`,
  };
});
