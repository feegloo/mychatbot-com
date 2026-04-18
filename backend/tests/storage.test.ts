import { describe, it, expect } from "vitest";
import { DiskStorageProvider } from "../src/storage/disk-storage";
import { S3StorageProvider } from "../src/storage/s3-storage";
import { createStorageProvider } from "../src/storage/index";
import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";

describe("DiskStorageProvider", () => {
  it("saves a file and returns storageKey and absolutePath", async () => {
    const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "storage-test-"));
    // Patch config.storageRoot temporarily via env
    const origRoot = process.env.STORAGE_ROOT;
    process.env.STORAGE_ROOT = tmpDir;

    // DiskStorageProvider reads config at import time, so we use it directly with a known dir
    const provider = new DiskStorageProvider();
    // Override the config import: we rely on the provider using config.storageRoot
    // Instead, just test the interface contract
    const result = await provider.save("test-ns", "hello.txt", {
      originalName: "hello.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("Hello, World!"),
    });

    expect(result.storageKey).toContain("hello");
    expect(result.storageKey).toMatch(/hello_[A-Za-z0-9]+\.txt$/);
    expect(result.absolutePath).toBeDefined();

    const content = await fs.readFile(result.absolutePath!, "utf-8");
    expect(content).toBe("Hello, World!");

    // Cleanup
    await fs.rm(tmpDir, { recursive: true });
    if (origRoot !== undefined) process.env.STORAGE_ROOT = origRoot;
    else delete process.env.STORAGE_ROOT;
  });
});

describe("S3StorageProvider", () => {
  it("returns a storage key with namespace prefix", async () => {
    const provider = new S3StorageProvider();
    const result = await provider.save("my-ns", "doc.pdf", {
      originalName: "doc.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("fake"),
    });
    expect(result.storageKey).toContain("my-ns/");
    expect(result.storageKey).toContain("doc.pdf");
  });
});

describe("createStorageProvider", () => {
  it("returns DiskStorageProvider by default", () => {
    const provider = createStorageProvider();
    expect(provider).toBeInstanceOf(DiskStorageProvider);
  });
});
