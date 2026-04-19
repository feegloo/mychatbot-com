import request from "supertest";
import { describe, it, expect, vi } from "vitest";
import { createApp } from "../src/app.js";

describe("request timing", () => {
  it("health endpoint responds within 500ms", async () => {
    const app = createApp().callback();
    const start = Date.now();
    const response = await request(app).get("/api/health");
    const duration = Date.now() - start;

    expect(response.status).toBe(200);
    expect(duration).toBeLessThan(500);
  });

  it("unknown API routes respond within 500ms", async () => {
    const app = createApp().callback();
    const start = Date.now();
    const response = await request(app).get("/api/nonexistent");
    const duration = Date.now() - start;

    expect(response.status).toBeDefined();
    expect(duration).toBeLessThan(500);
  });
});
