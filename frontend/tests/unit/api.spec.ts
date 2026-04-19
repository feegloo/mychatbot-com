import { describe, it, expect, vi } from "vitest";

// Mock import.meta.env before importing api module
vi.stubGlobal("import", { meta: { env: { VITE_API_BASE_URL: "http://localhost:3000/api" } } });

// We need to test the URL builder functions. Since they use import.meta.env,
// we test the logic directly.
describe("API URL builders", () => {
  const BASE = "http://localhost:3000";

  describe("getStorageUrl", () => {
    it("builds correct storage URL", async () => {
      const { getStorageUrl } = await import("../../src/api");
      const url = getStorageUrl("abc123", "report.pdf");
      expect(url).toBe(`${BASE}/api/storage/abc123/report.pdf`);
    });

    it("encodes special characters in file name", async () => {
      const { getStorageUrl } = await import("../../src/api");
      const url = getStorageUrl("abc123", "my file (1).pdf");
      expect(url).toContain("my%20file%20(1).pdf");
    });
  });
});
