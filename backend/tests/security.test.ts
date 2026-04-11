import { describe, it, expect } from "vitest";
import { deriveToken } from "../src/security";

describe("deriveToken", () => {
  it("returns a 64-char hex string (SHA-256)", () => {
    const token = deriveToken("conv123", "salt456");
    expect(token).toMatch(/^[0-9a-f]{64}$/);
  });

  it("is deterministic for same inputs", () => {
    const a = deriveToken("conv123", "salt456");
    const b = deriveToken("conv123", "salt456");
    expect(a).toBe(b);
  });

  it("produces different tokens for different salts", () => {
    const a = deriveToken("conv123", "salt-owner");
    const b = deriveToken("conv123", "salt-owner:editor");
    expect(a).not.toBe(b);
  });

  it("produces different tokens for different conversation IDs", () => {
    const a = deriveToken("conv111", "salt");
    const b = deriveToken("conv222", "salt");
    expect(a).not.toBe(b);
  });
});
