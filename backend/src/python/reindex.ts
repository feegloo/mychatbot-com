import path from "node:path";
import fs from "node:fs";
import { config } from "../config.js";
import { downloadConversationFiles } from "../storage/gcs-storage.js";
import { query } from "../db.js";
import type { UploadedFileRecord } from "../types.js";

/**
 * Check if a Chroma collection has data. If empty (e.g. after Cloud Run container restart),
 * re-index from the files still on disk (or download from GCS first).
 * Returns true if reindexing was triggered, false if collection was already populated.
 */
export async function ensureCollectionIndexed(conversationId: string, collectionName: string): Promise<boolean> {
  // Check collection count via Python server
  const countResp = await fetch(`${config.pythonServerUrl}/collection-count/${encodeURIComponent(collectionName)}`);
  if (!countResp.ok) return false;

  const { count } = await countResp.json() as { count: number };
  if (count > 0) return false;

  // Collection is empty — gather files for re-indexing
  let files: string[] = [];

  const storageDir = path.join(config.storageRoot, conversationId);

  // Check if files exist on local disk
  if (fs.existsSync(storageDir)) {
    files = fs.readdirSync(storageDir)
      .map(f => path.join(storageDir, f))
      .filter(f => fs.statSync(f).isFile());
  }

  // If no local files and GCS is configured, download from GCS
  if (!files.length && config.storageProvider === "gcs" && config.gcsBucket) {
    const result = await query<UploadedFileRecord>(
      `SELECT storage_key FROM uploaded_files WHERE conversation_id = $1`,
      [conversationId]
    );
    const storageKeys = result.rows.map(r => r.storage_key).filter(Boolean);
    if (storageKeys.length) {
      console.log(`[reindex] Downloading ${storageKeys.length} file(s) from GCS for ${collectionName}...`);
      files = await downloadConversationFiles(conversationId, storageKeys);
    }
  }

  if (!files.length) {
    console.warn(`[reindex] Collection ${collectionName} is empty and no files available for re-indexing`);
    return false;
  }

  console.log(`[reindex] Collection ${collectionName} is empty — re-indexing ${files.length} file(s)...`);

  const indexResp = await fetch(`${config.pythonServerUrl}/index`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      conversation_id: conversationId,
      collection_name: collectionName,
      file_paths: files,
    }),
  });

  if (!indexResp.ok) {
    const text = await indexResp.text();
    console.error(`[reindex] Re-indexing failed: ${text}`);
    return false;
  }

  console.log(`[reindex] Re-indexing complete for ${collectionName}`);
  return true;
}
