import request from "supertest";
import { describe, it, expect } from "vitest";
import { createApp } from "../src/app.js";

describe("app", () => {
  it("returns health", async () => {
    const app = createApp().callback();
    const response = await request(app).get("/api/health");
    expect(response.status).toBe(200);
    expect(response.body.ok).toBe(true);
  });
});
