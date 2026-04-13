export interface SavedObject {
  storageKey: string;
  absolutePath?: string;
}

export interface UploadFile {
  originalName: string;
  mimeType: string;
  buffer: Buffer;
}

export interface StorageProvider {
  save(namespace: string, fileName: string, file: UploadFile): Promise<SavedObject>;
}
