import fs from "node:fs/promises";
import path from "node:path";
import { generateShortId } from "../utils/id.js";
import { config } from "../config.js";
import type { StorageProvider, UploadFile } from "./storage-provider.js";

export class DiskStorageProvider implements StorageProvider {
  async save(namespace: string, fileName: string, file: UploadFile) {
    const dir = path.join(config.storageRoot, namespace);
    await fs.mkdir(dir, { recursive: true });

    const ext = path.extname(fileName);
    const base = path.basename(fileName, ext);
    const storedName = `${base}_${generateShortId()}${ext}`;
    const absolutePath = path.join(dir, storedName);

    await fs.writeFile(absolutePath, file.buffer);

    return {
      storageKey: path.relative(config.storageRoot, absolutePath),
      absolutePath
    };
  }
}
