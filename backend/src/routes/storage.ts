import Router from "@koa/router";
import path from "node:path";
import fs from "node:fs/promises";
import { config } from "../config.js";

export const storageRouter = new Router();

/** Decode a URI component, returning the original string if decoding fails or is a no-op. */
function safeDecodeURI(value: string): string {
  try {
    const decoded = decodeURIComponent(value);
    return decoded;
  } catch {
    return value;
  }
}

/**
 * Try to find a file in a directory that matches the target name,
 * accounting for NFC/NFD Unicode normalization differences.
 * Returns the actual filename on disk, or null if not found.
 */
async function findFileInDir(dir: string, targetName: string): Promise<string | null> {
  try {
    const entries = await fs.readdir(dir);
    const nfcTarget = targetName.normalize("NFC");
    const nfdTarget = targetName.normalize("NFD");
    for (const entry of entries) {
      if (entry === targetName) return entry;
      const nfcEntry = entry.normalize("NFC");
      if (nfcEntry === nfcTarget || nfcEntry === nfdTarget) return entry;
    }
  } catch {
    // Directory doesn't exist or isn't readable
  }
  return null;
}

/**
 * GET /storage/:conversationId/:fileName
 * Serves uploaded files and extracted images from the storage directory.
 * Only allows image files (png, jpg, jpeg, gif, webp) for security.
 */
storageRouter.get("/storage/:conversationId/:fileName", async (ctx) => {
  const { conversationId } = ctx.params;
  // Explicitly decode the fileName param to handle cases where the router
  // or an intermediate proxy didn't fully decode percent-encoded characters.
  const fileName = safeDecodeURI(ctx.params.fileName).normalize("NFC");

  // Validate conversationId is a 12-char base62 string (prevents path traversal)
  if (!/^[0-9A-Za-z]{16}$/.test(conversationId)) {
    ctx.status = 400;
    ctx.body = { error: "Invalid conversation ID" };
    return;
  }

  // Allow image, document, and text file extensions for preview
  const ext = path.extname(fileName).toLowerCase();
  const allowedExts = new Set([".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".txt"]);
  if (!allowedExts.has(ext)) {
    ctx.status = 403;
    ctx.body = { error: "File type not allowed" };
    return;
  }

  // Sanitize fileName to prevent path traversal
  const safeName = path.basename(fileName);
  const dir = path.join(config.storageRoot, conversationId);
  let filePath = path.join(dir, safeName);

  // Ensure resolved path is within storage root
  const resolved = path.resolve(filePath);
  if (!resolved.startsWith(path.resolve(config.storageRoot))) {
    ctx.status = 403;
    ctx.body = { error: "Access denied" };
    return;
  }

  // Try exact match first, then fallback to NFC/NFD-aware directory scan
  try {
    await fs.access(filePath);
  } catch {
    const actualName = await findFileInDir(dir, safeName);
    if (actualName) {
      filePath = path.join(dir, actualName);
    } else {
      ctx.status = 404;
      ctx.body = { error: "File not found" };
      return;
    }
  }

  const mimeTypes: Record<string, string> = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".txt": "text/plain; charset=utf-8",
  };

  ctx.set("Content-Type", mimeTypes[ext] || "application/octet-stream");
  if (ext === ".pdf" || ext === ".txt") {
    ctx.set("Content-Disposition", `inline; filename="${encodeURIComponent(fileName)}"`);
    ctx.set("X-Content-Type-Options", "nosniff");
    ctx.set("Accept-Ranges", "bytes");
  }
  ctx.set("Cache-Control", "public, max-age=86400");
  ctx.body = await fs.readFile(filePath);
});
