import type { StorageProvider, UploadFile } from "./storage-provider.js";

/**
 * Stub for later S3 migration.
 * Replace with @aws-sdk/client-s3 upload logic when ready.
 */
export class S3StorageProvider implements StorageProvider {
  async save(namespace: string, fileName: string, file: UploadFile) {
    const storageKey = `${namespace}/${Date.now()}_${fileName}`;
    void file;
    return {
      storageKey
    };
  }
}
