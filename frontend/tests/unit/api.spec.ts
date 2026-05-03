import { describe, it, expect, vi } from "vitest";

// We need to test the URL builder functions. Since they use import.meta.env,
// we test the logic directly.
describe("API URL builders", () => {
  describe("getStorageUrl", () => {
    it("builds correct storage URL", async () => {
      const { getStorageUrl } = await import("../../src/api");
      const url = getStorageUrl("abc123", "report.pdf");
      // VITE_API_BASE_URL is not configured in the test environment so
      // getBaseUrl() falls back to '' (relative URL base).
      expect(url).toBe(`/api/storage/abc123/report.pdf`);
    });

    it("encodes special characters in file name", async () => {
      const { getStorageUrl } = await import("../../src/api");
      const url = getStorageUrl("abc123", "my file (1).pdf");
      expect(url).toContain("my%20file%20(1).pdf");
    });
  });
});
