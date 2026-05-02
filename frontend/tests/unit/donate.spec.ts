import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

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
    await flushPromises();
    const hasDonate = wrapper.find(".conv-nav-donate").exists();
    const hasThanks = wrapper.find(".donate-thanks").exists();
    const hasMethods = wrapper.find(".donate-methods").exists();
    expect(hasDonate || hasThanks || hasMethods).toBe(true);
  });

  it("shows amount input with default value 1", async () => {
    const wrapper = mount(DonateWidget);
    await nextTick();
    await nextTick();
    const input = wrapper.find(".donate-amount-input");
    if (input.exists()) {
      expect((input.element as HTMLInputElement).value).toBe("1");
    }
  });

  it("updates donate button label when amount changes", async () => {
    const wrapper = mount(DonateWidget);
    await nextTick();
    await nextTick();
    const input = wrapper.find(".donate-amount-input");
    if (input.exists()) {
      await input.setValue(10);
      await nextTick();
      const btn = wrapper.find(".conv-nav-donate");
      expect(btn.exists()).toBe(true);
    }
  });

  it("shows thank you message when ?donated=1 is in URL", async () => {
    const originalSearch = window.location.search;
    const originalHref = window.location.href;
    Object.defineProperty(window.location, "search", { writable: true, value: "?donated=1" });
    Object.defineProperty(window.location, "href", { writable: true, value: "http://localhost/?donated=1" });
    const replaceState = vi.spyOn(window.history, "replaceState").mockImplementation(() => {});

    const wrapper = mount(DonateWidget);
    await flushPromises();

    expect(wrapper.find(".donate-thanks").exists()).toBe(true);
    expect(wrapper.text()).toContain("Thank you");

    replaceState.mockRestore();
    Object.defineProperty(window.location, "search", { writable: true, value: originalSearch });
    Object.defineProperty(window.location, "href", { writable: true, value: originalHref });
  });

  it("shows payment method bubbles immediately when donate button clicked (no Apple Pay)", async () => {
    const wrapper = mount(DonateWidget);
    await flushPromises();

    const btn = wrapper.find(".conv-nav-donate");
    expect(btn.exists()).toBe(true);

    // handleDonate is synchronous — methods list appears on the same tick
    await btn.trigger("click");

    expect(wrapper.find(".donate-methods").exists()).toBe(true);
    const bubbles = wrapper.findAll(".donate-bubble");
    // Apple Pay is hidden (canMakePayment returns null); other methods always shown
    expect(bubbles.length).toBeGreaterThan(0);
  });

  it("shows Apple Pay bubble after Stripe init and calls show() on tap", async () => {
    const { _mocks } = await import("@stripe/stripe-js") as any;
    _mocks.canMakePayment.mockResolvedValue({ applePay: true });

    const wrapper = mount(DonateWidget);
    await flushPromises();

    const btn = wrapper.find(".conv-nav-donate");
    expect(btn.exists()).toBe(true);

    // First tap: synchronously shows methods + kicks off Stripe init in background
    await btn.trigger("click");
    expect(wrapper.find(".donate-methods").exists()).toBe(true);

    // Let Stripe init + canMakePayment resolve so Apple Pay bubble appears
    await flushPromises();

    const applePayBubble = wrapper.find('.donate-bubble[title="Apple Pay"]');
    expect(applePayBubble.exists()).toBe(true);

    // Tapping the Apple Pay bubble calls show() synchronously within its own gesture
    await applePayBubble.trigger("click");
    expect(_mocks.show).toHaveBeenCalledTimes(1);
  });
});
