import { config } from "../config.js";
import { DiskStorageProvider } from "./disk-storage.js";
import { GcsStorageProvider } from "./gcs-storage.js";
import { S3StorageProvider } from "./s3-storage.js";

export function createStorageProvider() {
  switch (config.storageProvider) {
    case "gcs": return new GcsStorageProvider();
    case "s3":  return new S3StorageProvider();
    default:    return new DiskStorageProvider();
  }
}
