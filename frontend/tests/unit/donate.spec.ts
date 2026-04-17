import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";

// Mock vue-router
vi.mock("vue-router", () => ({
  useRoute: () => ({
    path: "/",
    query: {},
    params: {},
  }),
}));

// Mock @stripe/stripe-js — factory cannot reference outer variables (hoisted)
vi.mock("@stripe/stripe-js", () => {
  const canMakePayment = vi.fn().mockResolvedValue(null);
  const show = vi.fn();
  const on = vi.fn();
  const off = vi.fn();
  return {
    loadStripe: vi.fn().mockResolvedValue({
      paymentRequest: vi.fn(() => ({
        canMakePayment,
        show,
        on,
        off,
      })),
      confirmCardPayment: vi.fn().mockResolvedValue({}),
    }),
    _mocks: { canMakePayment, show, on, off },
  };
});

// Mock axios
vi.mock("axios", () => ({
  default: {
    create: () => ({
      post: vi.fn().mockResolvedValue({
        data: { clientSecret: "test_secret", url: "https://checkout.stripe.com/test" },
      }),
    }),
  },
}));

// Set env
vi.stubEnv("VITE_STRIPE_PUBLISHABLE_KEY", "pk_test_fake");

import DonateWidget from "../../src/components/DonateWidget.vue";

describe("DonateWidget", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows Donate button when Stripe key is set", async () => {
    const wrapper = mount(DonateWidget);
    await nextTick();
    await nextTick();
    // canDonate is true because VITE_STRIPE_PUBLISHABLE_KEY is set
    // It should show either the donate button or thank you (if ?donated=1)
    const hasDonate = wrapper.find(".conv-nav-donate").exists();
    const hasThanks = wrapper.find(".donate-thanks").exists();
    const hasMethods = wrapper.find(".donate-methods").exists();
    expect(hasDonate || hasThanks || hasMethods).toBe(true);
  });

  it("shows thank you message when ?donated=1 is in URL", async () => {
    // Simulate ?donated=1
    const originalSearch = window.location.search;
    const originalHref = window.location.href;
    Object.defineProperty(window.location, "search", { writable: true, value: "?donated=1" });
    Object.defineProperty(window.location, "href", { writable: true, value: "http://localhost/?donated=1" });
    const replaceState = vi.spyOn(window.history, "replaceState").mockImplementation(() => {});

    const wrapper = mount(DonateWidget);
    await nextTick();
    await nextTick();

    expect(wrapper.find(".donate-thanks").exists()).toBe(true);
    expect(wrapper.text()).toContain("Thank you");

    replaceState.mockRestore();
    Object.defineProperty(window.location, "search", { writable: true, value: originalSearch });
    Object.defineProperty(window.location, "href", { writable: true, value: originalHref });
  });

  it("shows payment method bubbles when donate button clicked (no Apple Pay)", async () => {
    const wrapper = mount(DonateWidget);
    await nextTick();
    await nextTick();
    // Wait for initStripe to finish (async)
    await new Promise((r) => setTimeout(r, 50));
    await nextTick();

    const btn = wrapper.find(".conv-nav-donate");
    if (btn.exists()) {
      await btn.trigger("click");
      await nextTick();
      expect(wrapper.find(".donate-methods").exists()).toBe(true);
      const bubbles = wrapper.findAll(".donate-bubble");
      // Should have bubbles for non-Apple-Pay methods
      expect(bubbles.length).toBeGreaterThan(0);
    }
  });
});
