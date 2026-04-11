import { describe, it, expect } from "vitest";
import { generateShortId } from "../src/utils/id";

describe("generateShortId", () => {
  it("returns a 16-character string by default", () => {
    const id = generateShortId();
    expect(id).toHaveLength(16);
  });

  it("uses only base62 characters", () => {
    for (let i = 0; i < 20; i++) {
      const id = generateShortId();
      expect(id).toMatch(/^[0-9A-Za-z]+$/);
    }
  });

  it("respects custom length", () => {
    expect(generateShortId(8)).toHaveLength(8);
    expect(generateShortId(32)).toHaveLength(32);
  });

  it("generates unique IDs", () => {
    const ids = new Set(Array.from({ length: 100 }, () => generateShortId()));
    expect(ids.size).toBe(100);
  });
});
