import request from "supertest";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { createApp } from "../src/app.js";

// Mock Stripe
vi.mock("stripe", () => {
  const mockStripe = vi.fn(() => ({
    paymentIntents: {
      create: vi.fn().mockResolvedValue({
        client_secret: "pi_test_secret_123",
      }),
    },
    checkout: {
      sessions: {
        create: vi.fn().mockResolvedValue({
          url: "https://checkout.stripe.com/test_session",
        }),
        retrieve: vi.fn().mockResolvedValue({
          payment_status: "paid",
        }),
      },
    },
  }));
  return { default: mockStripe };
});

// Mock config to have a Stripe key
vi.mock("../src/config.js", () => ({
  config: {
    stripeSecretKey: "sk_test_fake",
    stripeWebhookSecret: "",
    frontendDistPath: "",
    port: 3000,
    publicBaseUrl: "http://localhost:3000",
    databaseUrl: "",
    storageProvider: "disk",
    storageRoot: "/tmp",
    pythonBin: "python3",
    pythonProjectRoot: "/tmp",
    pythonIndexingMode: "script",
    chromaMode: "local",
    chromaHttpHost: "",
    chromaPersistDir: "/tmp",
    chromaApiKey: "",
    chromaTenant: "",
    chromaDatabase: "",
    openAiApiKey: "",
    openAiChatModel: "",
    openAiEmbeddingModel: "",
    pythonServerUrl: "",
    gcsBucket: "",
    logsRoot: "/tmp",
    debugUser: "admin",
    debugPass: "admin",
  },
}));

describe("donate endpoints", () => {
  let app: ReturnType<typeof createApp>;

  beforeEach(() => {
    app = createApp();
  });

  it("POST /api/donate returns clientSecret", async () => {
    const res = await request(app.callback()).post("/api/donate");
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty("clientSecret");
    expect(res.body.clientSecret).toBe("pi_test_secret_123");
  });

  it("POST /api/donate/checkout returns checkout URL", async () => {
    const res = await request(app.callback())
      .post("/api/donate/checkout")
      .send({ returnUrl: "https://chatrag.app" });
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty("url");
    expect(res.body.url).toContain("checkout.stripe.com");
  });

  it("GET /api/donate/status/:sessionId returns payment status", async () => {
    const res = await request(app.callback()).get(
      "/api/donate/status/cs_test_123"
    );
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty("status");
    expect(res.body.status).toBe("paid");
  });
});
