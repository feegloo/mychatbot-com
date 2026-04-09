import Router from "@koa/router";
import path from "node:path";
import fs from "node:fs/promises";
import { config } from "../config.js";

export const storageRouter = new Router();

/**
 * GET /storage/:conversationId/:fileName
 * Serves uploaded files and extracted images from the storage directory.
 * Only allows image files (png, jpg, jpeg, gif, webp) for security.
 */
storageRouter.get("/storage/:conversationId/:fileName", async (ctx) => {
  const { conversationId, fileName } = ctx.params;

  // Validate conversationId is a UUID pattern (prevents path traversal)
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(conversationId)) {
    ctx.status = 400;
    ctx.body = { error: "Invalid conversation ID" };
    return;
  }

  // Only allow image file extensions
  const ext = path.extname(fileName).toLowerCase();
  const allowedExts = new Set([".png", ".jpg", ".jpeg", ".gif", ".webp"]);
  if (!allowedExts.has(ext)) {
    ctx.status = 403;
    ctx.body = { error: "Only image files can be served" };
    return;
  }

  // Sanitize fileName to prevent path traversal
  const safeName = path.basename(fileName);
  const filePath = path.join(config.storageRoot, conversationId, safeName);

  // Ensure resolved path is within storage root
  const resolved = path.resolve(filePath);
  if (!resolved.startsWith(path.resolve(config.storageRoot))) {
    ctx.status = 403;
    ctx.body = { error: "Access denied" };
    return;
  }

  try {
    await fs.access(filePath);
  } catch {
    ctx.status = 404;
    ctx.body = { error: "File not found" };
    return;
  }

  const mimeTypes: Record<string, string> = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
  };

  ctx.set("Content-Type", mimeTypes[ext] || "application/octet-stream");
  ctx.set("Cache-Control", "public, max-age=86400");
  ctx.body = await fs.readFile(filePath);
});
