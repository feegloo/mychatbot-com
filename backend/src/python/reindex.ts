import path from "node:path";
import fs from "node:fs";
import { config } from "../config.js";

/**
 * Check if a Chroma collection has data. If empty (e.g. after Cloud Run container restart),
 * re-index from the files still on disk.
 * Returns true if reindexing was triggered, false if collection was already populated.
 */
export async function ensureCollectionIndexed(conversationId: string, collectionName: string): Promise<boolean> {
  // Check collection count via Python server
  const countResp = await fetch(`${config.pythonServerUrl}/collection-count/${encodeURIComponent(collectionName)}`);
  if (!countResp.ok) return false;

  const { count } = await countResp.json() as { count: number };
  if (count > 0) return false;

  // Collection is empty — try to re-index from disk storage
  const storageDir = path.join(config.storageRoot, conversationId);
  if (!fs.existsSync(storageDir)) {
    console.warn(`[reindex] Collection ${collectionName} is empty and storage dir ${storageDir} not found — files lost after deploy`);
    return false;
  }

  const files = fs.readdirSync(storageDir)
    .map(f => path.join(storageDir, f))
    .filter(f => fs.statSync(f).isFile());

  if (!files.length) {
    console.warn(`[reindex] Collection ${collectionName} is empty and no files in ${storageDir}`);
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
