import path from "node:path";
import fs from "node:fs/promises";
import { Storage } from "@google-cloud/storage";
import { generateShortId } from "../utils/id.js";
import { config } from "../config.js";
import type { StorageProvider, UploadFile } from "./storage-provider.js";

let _gcsClient: Storage | null = null;
function getGcsClient(): Storage {
  if (!_gcsClient) {
    _gcsClient = new Storage();
  }
  return _gcsClient;
}

export class GcsStorageProvider implements StorageProvider {
  async save(namespace: string, fileName: string, file: UploadFile) {
    const ext = path.extname(fileName);
    const base = path.basename(fileName, ext);
    const storedName = `${base}_${generateShortId()}${ext}`;
    const gcsKey = `${namespace}/${storedName}`;

    // Upload to GCS
    const bucket = getGcsClient().bucket(config.gcsBucket);
    const blob = bucket.file(gcsKey);
    await blob.save(file.buffer, {
      contentType: file.mimeType,
      resumable: false,
      metadata: {
        metadata: {
          created_at: new Date().toISOString(),
          size: String(file.buffer.length),
          original_name: file.originalName,
        },
      },
    });

    // Also write to local disk so Python indexing can read it immediately
    const localDir = path.join(config.storageRoot, namespace);
    await fs.mkdir(localDir, { recursive: true });
    const absolutePath = path.join(localDir, storedName);
    await fs.writeFile(absolutePath, file.buffer);

    return {
      storageKey: gcsKey,
      absolutePath,
    };
  }
}

/**
 * Download a file from GCS to a local path. Returns the local path.
 */
export async function downloadFromGcs(gcsKey: string, localPath: string): Promise<string> {
  const dir = path.dirname(localPath);
  await fs.mkdir(dir, { recursive: true });
  const bucket = getGcsClient().bucket(config.gcsBucket);
  await bucket.file(gcsKey).download({ destination: localPath });
  return localPath;
}

/**
 * Read a file from GCS as a Buffer.
 */
export async function readFromGcs(gcsKey: string): Promise<Buffer> {
  const bucket = getGcsClient().bucket(config.gcsBucket);
  const [contents] = await bucket.file(gcsKey).download();
  return contents;
}

/**
 * Download all files for a conversation from GCS to a local directory.
 * Returns the list of local absolute paths.
 */
export async function downloadConversationFiles(conversationId: string, storageKeys: string[]): Promise<string[]> {
  const localDir = path.join(config.storageRoot, conversationId);
  await fs.mkdir(localDir, { recursive: true });

  const localPaths: string[] = [];
  for (const key of storageKeys) {
    const fileName = path.basename(key);
    const localPath = path.join(localDir, fileName);
    try {
      await fs.access(localPath);
      // Already downloaded
    } catch {
      await downloadFromGcs(key, localPath);
    }
    localPaths.push(localPath);
  }
  return localPaths;
}
