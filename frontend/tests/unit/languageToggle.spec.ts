import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { nextTick } from "vue";

// Mock the api module
const detectLanguageMock = vi.fn();
const translateTextsMock = vi.fn();

vi.mock("../../src/api", () => ({
  detectLanguage: (...args: unknown[]) => detectLanguageMock(...args),
  translateTexts: (...args: unknown[]) => translateTextsMock(...args),
}));

import LanguageToggle from "../../src/components/LanguageToggle.vue";

function makeMessages(contents: string[], role = "assistant") {
  return contents.map(c => ({ role, content: c }));
}

describe("LanguageToggle", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    detectLanguageMock.mockResolvedValue({ language: "en", confidence: 0.99 });
    translateTextsMock.mockImplementation(async (texts: string[]) => ({
      translations: texts.map(t => `[translated] ${t}`),
    }));
  });

  // ── Visibility ──

  describe("visibility", () => {
    it("is hidden when no messages", async () => {
      const wrapper = mount(LanguageToggle, {
        props: { messages: [] },
      });
      await flushPromises();
      expect(wrapper.find(".lang-toggle-wrap").exists()).toBe(false);
    });

    it("is hidden when assistant message is too short", async () => {
      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["short"]) },
      });
      await flushPromises();
      expect(wrapper.find(".lang-toggle-wrap").exists()).toBe(false);
    });

    it("is hidden when detected=en, browser=en (only 1 lang)", async () => {
      // navigator.language is mocked as 'en' by default in happy-dom
      Object.defineProperty(navigator, "language", { value: "en", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "en", confidence: 0.99 });

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["This is a long enough English message for detection."]) },
      });
      await flushPromises();
      await nextTick();
      // available = {en} — only 1 lang
      expect(wrapper.find(".lang-toggle-wrap").exists()).toBe(false);
    });

    it("shows when detected=pl, browser=pl (English always available)", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "pl", confidence: 0.99 });

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["To jest wystarczająco długa polska wiadomość do wykrycia."]) },
      });
      await flushPromises();
      await nextTick();
      // available = {pl, en} — 2 langs
      expect(wrapper.find(".lang-toggle-wrap").exists()).toBe(true);
    });

    it("shows when detected=en, browser=pl", async () => {
      Object.defineProperty(navigator, "language", { value: "pl-PL", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "en", confidence: 0.99 });

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["This is a long enough English message for detection."]) },
      });
      await flushPromises();
      await nextTick();
      // available = {en, pl} — 2 langs
      expect(wrapper.find(".lang-toggle-wrap").exists()).toBe(true);
    });

    it("shows when detected=hi, browser=pl (3 langs: hi, pl, en)", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "hi", confidence: 0.95 });

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["यह एक काफी लंबा हिंदी संदेश है जो भाषा का पता लगाने के लिए पर्याप्त है।"]) },
      });
      await flushPromises();
      await nextTick();
      expect(wrapper.find(".lang-toggle-wrap").exists()).toBe(true);
    });
  });

  // ── Toggle mode (2 languages) ──

  describe("toggle mode (2 languages)", () => {
    it("toggles between detected and other language on click", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "en", confidence: 0.99 });

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["This is a long enough English message for detection."]) },
      });
      await flushPromises();
      await nextTick();

      const vm = wrapper.vm as any;
      expect(vm.currentLang).toBe("en");
      expect(vm.isTranslated).toBe(false);

      // Click to translate to Polish
      await wrapper.find(".lang-toggle-btn").trigger("click");
      await flushPromises();

      expect(vm.currentLang).toBe("pl");
      expect(vm.isTranslated).toBe(true);
      expect(wrapper.emitted("translated")).toBeTruthy();
    });

    it("toggles back to original on second click", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "en", confidence: 0.99 });

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["This is a long enough English message for detection."]) },
      });
      await flushPromises();
      await nextTick();

      // First click: translate
      await wrapper.find(".lang-toggle-btn").trigger("click");
      await flushPromises();
      expect((wrapper.vm as any).currentLang).toBe("pl");

      // Second click: restore
      await wrapper.find(".lang-toggle-btn").trigger("click");
      await flushPromises();
      expect((wrapper.vm as any).currentLang).toBe("en");
      expect(wrapper.emitted("restored")).toBeTruthy();
    });

    it("does not show dropdown in toggle mode", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "en", confidence: 0.99 });

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["This is a long enough English message for detection."]) },
      });
      await flushPromises();
      await nextTick();

      // Click should not show dropdown, should directly translate
      await wrapper.find(".lang-toggle-btn").trigger("click");
      await flushPromises();
      expect(wrapper.find(".lang-dropdown").exists()).toBe(false);
    });

    it("Polish doc + Polish browser → toggle translates to English", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "pl", confidence: 0.99 });

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["To jest wystarczająco długa polska wiadomość do wykrycia."]) },
      });
      await flushPromises();
      await nextTick();

      const vm = wrapper.vm as any;
      // available = {pl, en}, detected = pl, so toggle target = en
      expect(vm.availableLangs).toContain("en");
      expect(vm.availableLangs).toContain("pl");
      expect(vm.availableLangs.length).toBe(2);

      await wrapper.find(".lang-toggle-btn").trigger("click");
      await flushPromises();

      expect(vm.currentLang).toBe("en");
      expect(translateTextsMock).toHaveBeenCalled();
      // Check that targetLang was 'en'
      const callArgs = translateTextsMock.mock.calls[0];
      expect(callArgs[1]).toBe("en");
    });
  });

  // ── Dropdown mode (3+ languages) ──

  describe("dropdown mode (3+ languages)", () => {
    it("shows dropdown on first click for 3-language scenario", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "hi", confidence: 0.95 });

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["यह एक काफी लंबा हिंदी संदेश है जो भाषा का पता लगाने के लिए पर्याप्त है।"]) },
      });
      await flushPromises();
      await nextTick();

      const vm = wrapper.vm as any;
      expect(vm.availableLangs.length).toBe(3);
      expect(vm.availableLangs).toContain("hi");
      expect(vm.availableLangs).toContain("pl");
      expect(vm.availableLangs).toContain("en");

      // Click opens dropdown
      await wrapper.find(".lang-toggle-btn").trigger("click");
      expect(wrapper.find(".lang-dropdown").exists()).toBe(true);
    });

    it("dropdown shows options except current language", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "hi", confidence: 0.95 });

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["यह एक काफी लंबा हिंदी संदेश है जो भाषा का पता लगाने के लिए पर्याप्त है।"]) },
      });
      await flushPromises();
      await nextTick();

      await wrapper.find(".lang-toggle-btn").trigger("click");
      const items = wrapper.findAll(".lang-dropdown-item");
      // Current is 'hi', so should show pl and en
      expect(items.length).toBe(2);
      const texts = items.map(i => i.text());
      expect(texts.some(t => t.includes("Polski"))).toBe(true);
      expect(texts.some(t => t.includes("English"))).toBe(true);
    });

    it("clicking dropdown item translates to that language", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "hi", confidence: 0.95 });

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["यह एक काफी लंबा हिंदी संदेश है।"]) },
      });
      await flushPromises();
      await nextTick();

      // Open dropdown
      await wrapper.find(".lang-toggle-btn").trigger("click");

      // Click English option
      const items = wrapper.findAll(".lang-dropdown-item");
      const enItem = items.find(i => i.text().includes("English"));
      expect(enItem).toBeTruthy();
      await enItem!.trigger("click");
      await flushPromises();

      const vm = wrapper.vm as any;
      expect(vm.currentLang).toBe("en");
      expect(vm.isTranslated).toBe(true);
      expect(wrapper.find(".lang-dropdown").exists()).toBe(false);
    });

    it("clicking button when translated restores to original (detected)", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "hi", confidence: 0.95 });

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["यह एक काफी लंबा हिंदी संदेश है।"]) },
      });
      await flushPromises();
      await nextTick();

      // Translate to English via dropdown
      await wrapper.find(".lang-toggle-btn").trigger("click");
      const items = wrapper.findAll(".lang-dropdown-item");
      const enItem = items.find(i => i.text().includes("English"));
      await enItem!.trigger("click");
      await flushPromises();

      expect((wrapper.vm as any).currentLang).toBe("en");

      // Now click button again — should restore to original (hi)
      await wrapper.find(".lang-toggle-btn").trigger("click");
      await flushPromises();

      expect((wrapper.vm as any).currentLang).toBe("hi");
      expect((wrapper.vm as any).isTranslated).toBe(false);
      expect(wrapper.emitted("restored")).toBeTruthy();
    });
  });

  // ── Flag display ──

  describe("flag display", () => {
    it("shows detected language flag initially", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "en", confidence: 0.99 });

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["This is a long enough English message for detection."]) },
      });
      await flushPromises();
      await nextTick();

      expect(wrapper.find(".lang-flag").text()).toBe("🇬🇧");
    });

    it("shows target language flag after translation", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "en", confidence: 0.99 });

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["This is a long enough English message for detection."]) },
      });
      await flushPromises();
      await nextTick();

      await wrapper.find(".lang-toggle-btn").trigger("click");
      await flushPromises();

      expect(wrapper.find(".lang-flag").text()).toBe("🇵🇱");
    });

    it("flips flag optimistically on click before translation promise resolves", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "en", confidence: 0.99 });
      // Translation hangs — flag must still flip immediately
      let resolveTranslate!: (value: { translations: string[] }) => void;
      translateTextsMock.mockImplementation(
        () => new Promise(r => { resolveTranslate = r; }),
      );

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["This is a long enough English message for detection."]) },
      });
      await flushPromises();
      await nextTick();
      expect(wrapper.find(".lang-flag").text()).toBe("🇬🇧");

      await wrapper.find(".lang-toggle-btn").trigger("click");
      await nextTick();
      // Flag flipped even though translateTexts has not resolved
      expect(wrapper.find(".lang-flag").text()).toBe("🇵🇱");

      resolveTranslate({ translations: ["[translated]"] });
      await flushPromises();
      expect(wrapper.find(".lang-flag").text()).toBe("🇵🇱");
    });

    it("does not change flag when opening dropdown (3-language mode)", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "hi", confidence: 0.95 });

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["यह एक काफी लंबा हिंदी संदेश है जो भाषा का पता लगाने के लिए पर्याप्त है।"]) },
      });
      await flushPromises();
      await nextTick();
      expect(wrapper.find(".lang-flag").text()).toBe("🇮🇳");

      // Click button → just opens dropdown, no translation kicks off
      await wrapper.find(".lang-toggle-btn").trigger("click");
      await nextTick();
      expect(wrapper.find(".lang-dropdown").exists()).toBe(true);
      expect(wrapper.find(".lang-flag").text()).toBe("🇮🇳");
      expect(translateTextsMock).not.toHaveBeenCalled();

      // Pick a target from dropdown → flag flips immediately
      let resolveTranslate!: (value: { translations: string[] }) => void;
      translateTextsMock.mockImplementation(
        () => new Promise(r => { resolveTranslate = r; }),
      );
      const plItem = wrapper.findAll(".lang-dropdown-item").find(i => i.text().includes("Polski"));
      await plItem!.trigger("click");
      await nextTick();
      expect(wrapper.find(".lang-flag").text()).toBe("🇵🇱");

      resolveTranslate({ translations: ["[translated]"] });
      await flushPromises();
      expect(wrapper.find(".lang-flag").text()).toBe("🇵🇱");
    });
  });

  // ── Language detection ──

  describe("language detection", () => {
    it("detects language from first assistant message > 20 chars", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "de", confidence: 0.9 });

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["Dies ist eine ausreichend lange deutsche Nachricht zur Erkennung."]) },
      });
      await flushPromises();
      await nextTick();

      expect(detectLanguageMock).toHaveBeenCalledOnce();
      expect((wrapper.vm as any).detectedLang).toBe("de");
    });

    it("retries detection on failure", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockRejectedValueOnce(new Error("network"));

      const msgs = makeMessages(["This is a long enough English message for detection."]);
      const wrapper = mount(LanguageToggle, {
        props: { messages: msgs },
      });
      await flushPromises();
      await nextTick();

      expect((wrapper.vm as any).detectedLang).toBe("");

      // Now succeed on retry
      detectLanguageMock.mockResolvedValue({ language: "en", confidence: 0.99 });
      // Trigger watch by updating messages
      await wrapper.setProps({ messages: [...msgs, { role: "user", content: "new msg" }] });
      await flushPromises();
      await nextTick();

      expect((wrapper.vm as any).detectedLang).toBe("en");
    });

    it("skips user-only messages for detection", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });

      const _wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["This is a user message, long enough to detect language."], "user") },
      });
      await flushPromises();
      await nextTick();

      expect(detectLanguageMock).not.toHaveBeenCalled();
    });
  });

  // ── availableLangs computation ──

  describe("availableLangs", () => {
    it("deduplicates when detected=en, browser=en", async () => {
      Object.defineProperty(navigator, "language", { value: "en", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "en", confidence: 0.99 });

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["This is a long enough English message for detection."]) },
      });
      await flushPromises();
      await nextTick();

      const vm = wrapper.vm as any;
      expect(vm.availableLangs).toEqual(["en"]);
    });

    it("has 2 langs when detected=pl, browser=pl (en always added)", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "pl", confidence: 0.99 });

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["To jest wystarczająco długa polska wiadomość."]) },
      });
      await flushPromises();
      await nextTick();

      const vm = wrapper.vm as any;
      expect(vm.availableLangs.length).toBe(2);
      expect(vm.availableLangs).toContain("pl");
      expect(vm.availableLangs).toContain("en");
    });

    it("has 3 langs when all different: detected=hi, browser=pl, plus en", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "hi", confidence: 0.95 });

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["यह एक काफी लंबा हिंदी संदेश है जो पर्याप्त है।"]) },
      });
      await flushPromises();
      await nextTick();

      const vm = wrapper.vm as any;
      expect(vm.availableLangs.length).toBe(3);
      expect(new Set(vm.availableLangs)).toEqual(new Set(["hi", "pl", "en"]));
    });

    it("has 2 langs when detected=en, browser=fr (en deduped)", async () => {
      Object.defineProperty(navigator, "language", { value: "fr", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "en", confidence: 0.99 });

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["This is a sufficiently long English message."]) },
      });
      await flushPromises();
      await nextTick();

      const vm = wrapper.vm as any;
      expect(vm.availableLangs.length).toBe(2);
      expect(vm.availableLangs).toContain("en");
      expect(vm.availableLangs).toContain("fr");
    });
  });

  // ── Marker preservation ──

  describe("marker preservation", () => {
    it("preserves [source:X] markers through translation", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "en", confidence: 0.99 });
      translateTextsMock.mockImplementation(async (texts: string[]) => ({
        translations: texts.map(t => `PRZETŁUMACZONE: ${t}`),
      }));

      const wrapper = mount(LanguageToggle, {
        props: {
          messages: [{ role: "assistant", content: "Answer text [source:1] more text [source:2]" }],
        },
      });
      await flushPromises();
      await nextTick();

      await wrapper.find(".lang-toggle-btn").trigger("click");
      await flushPromises();

      const emitted = wrapper.emitted("translated")![0][0] as Map<number, string>;
      const translated = emitted.get(0)!;
      expect(translated).toContain("[source:1]");
      expect(translated).toContain("[source:2]");
    });

    it("preserves markdown image URLs through translation (never sent to translator)", async () => {
      // Pollinations-style URL: the prompt text lives in the URL path, so if it
      // reaches the translator the URL becomes invalid and the <img> breaks.
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "en", confidence: 0.99 });
      translateTextsMock.mockImplementation(async (texts: string[]) => ({
        translations: texts.map(t => `PL: ${t}`),
      }));

      const imageMd =
        "![A red cat](https://image.pollinations.ai/prompt/A%20red%20cat?seed=123)";
      const original = `Here is your picture: ${imageMd} Enjoy the result!`;
      const wrapper = mount(LanguageToggle, {
        props: { messages: [{ role: "assistant", content: original }] },
      });
      await flushPromises();
      await nextTick();

      await wrapper.find(".lang-toggle-btn").trigger("click");
      await flushPromises();

      // The image markdown must be replaced by an opaque placeholder before
      // hitting the translate API, so the URL is never exposed to translation.
      expect(translateTextsMock).toHaveBeenCalled();
      const sentTexts = translateTextsMock.mock.calls[0][0] as string[];
      expect(sentTexts[0]).not.toContain("pollinations");
      expect(sentTexts[0]).not.toContain("![");

      // Restored translation must contain the original image markdown verbatim.
      const emitted = wrapper.emitted("translated")![0][0] as Map<number, string>;
      const translated = emitted.get(0)!;
      expect(translated).toContain(imageMd);
    });

    it("preserves [poem] / [/poem] tags verbatim (never translated to 'wiersz' etc.)", async () => {
      // The literal tag tokens must be opaque so markdown.ts can still
      // recognise the block and render the styled poem layout after
      // translation. The verse content between the tags is still translated.
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "en", confidence: 0.99 });
      translateTextsMock.mockImplementation(async (texts: string[]) => ({
        translations: texts.map(t => `PL:${t}`),
      }));

      const original = "Here is a poem:\n[poem]\nRoses are red\nViolets are blue\n[/poem]\nEnjoy!";
      const wrapper = mount(LanguageToggle, {
        props: { messages: [{ role: "assistant", content: original }] },
      });
      await flushPromises();
      await nextTick();

      await wrapper.find(".lang-toggle-btn").trigger("click");
      await flushPromises();

      const sentTexts = translateTextsMock.mock.calls[0][0] as string[];
      expect(sentTexts[0]).not.toContain("[poem]");
      expect(sentTexts[0]).not.toContain("[/poem]");

      const emitted = wrapper.emitted("translated")![0][0] as Map<number, string>;
      const translated = emitted.get(0)!;
      expect(translated).toContain("[poem]");
      expect(translated).toContain("[/poem]");
      expect(translated).not.toContain("[wiersz]");
    });
  });

  // ── Whitespace preservation (prevents layout jump) ──

  describe("whitespace preservation", () => {
    it("strips leading/trailing whitespace before sending to translate API", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "en", confidence: 0.99 });
      translateTextsMock.mockImplementation(async (texts: string[]) => ({
        translations: texts.map(t => `T: ${t}`),
      }));

      const original = "\n\nHello world, this is a sufficiently long message.\n\n";
      const wrapper = mount(LanguageToggle, {
        props: { messages: [{ role: "assistant", content: original }] },
      });
      await flushPromises();
      await nextTick();

      await wrapper.find(".lang-toggle-btn").trigger("click");
      await flushPromises();

      // Translator must receive the stripped variant so whitespace is not sent to the
      // external API (which often collapses/strips it and causes layout jumps on restore).
      const sentTexts = translateTextsMock.mock.calls[0]?.[0] as string[];
      expect(sentTexts).toBeTruthy();
      expect(sentTexts[0]).toBe("Hello world, this is a sufficiently long message.");
    });
  });

  // ── Title translation ──

  describe("title translation", () => {
    it("sends title to the translate API when title prop is provided", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "pl", confidence: 0.99 });
      translateTextsMock.mockImplementation(async (texts: string[]) => ({
        translations: texts.map(t => `EN: ${t}`),
      }));

      const wrapper = mount(LanguageToggle, {
        props: {
          messages: makeMessages(["To jest wystarczająco długa polska wiadomość do wykrycia."]),
          title: "Światło nad eliksirem",
        },
      });
      await flushPromises();
      await nextTick();

      await wrapper.find(".lang-toggle-btn").trigger("click");
      await flushPromises();

      const titleCall = translateTextsMock.mock.calls.find(
        (args) => Array.isArray(args[0]) && (args[0] as string[])[0] === "Światło nad eliksirem",
      );
      expect(titleCall).toBeTruthy();
    });

    it("skips title translation when title is empty", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "pl", confidence: 0.99 });

      const wrapper = mount(LanguageToggle, {
        props: {
          messages: makeMessages(["To jest wystarczająco długa polska wiadomość do wykrycia."]),
          title: "   ",
        },
      });
      await flushPromises();
      await nextTick();

      await wrapper.find(".lang-toggle-btn").trigger("click");
      await flushPromises();

      // No call should contain just whitespace (title was empty after trim)
      const titleCalls = translateTextsMock.mock.calls.filter(
        (args) => Array.isArray(args[0]) && (args[0] as string[]).some((t) => !t.trim()),
      );
      expect(titleCalls.length).toBe(0);
    });
  });

  // ── Cancel / in-flight promise reuse ──

  describe("in-flight cancellation and reuse", () => {
    it("cancelling mid-translation restores the original flag without firing a new request", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "en", confidence: 0.99 });

      let resolveTranslate!: (value: { translations: string[] }) => void;
      translateTextsMock.mockImplementation(
        () => new Promise(r => { resolveTranslate = r; }),
      );

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["This is a long enough English message for detection."]) },
      });
      await flushPromises();
      await nextTick();

      // First click starts the translation (promise hangs)
      await wrapper.find(".lang-toggle-btn").trigger("click");
      await nextTick();
      expect(wrapper.find(".lang-flag").text()).toBe("🇵🇱"); // pending PL
      expect((wrapper.vm as any).translating).toBe(true);
      expect(translateTextsMock).toHaveBeenCalledTimes(1);

      // Second click while still loading = cancel visual (show original again)
      await wrapper.find(".lang-toggle-btn").trigger("click");
      await nextTick();
      expect(wrapper.find(".lang-flag").text()).toBe("🇬🇧"); // back to detected
      expect((wrapper.vm as any).translating).toBe(false);
      // Background request is NOT cancelled and NO new one was issued
      expect(translateTextsMock).toHaveBeenCalledTimes(1);

      // When the background request finally resolves, translations must NOT
      // be applied (user already backed out) — no 'translated' emission.
      resolveTranslate({ translations: ["[translated]"] });
      await flushPromises();
      expect(wrapper.emitted("translated")).toBeFalsy();
      expect((wrapper.vm as any).currentLang).toBe("en");
    });

    it("re-clicking same target while promise is in flight awaits the same promise", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "en", confidence: 0.99 });

      let resolveTranslate!: (value: { translations: string[] }) => void;
      translateTextsMock.mockImplementation(
        () => new Promise(r => { resolveTranslate = r; }),
      );

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["This is a long enough English message for detection."]) },
      });
      await flushPromises();
      await nextTick();

      // Click 1: start translation (hangs)
      await wrapper.find(".lang-toggle-btn").trigger("click");
      await nextTick();
      // Click 2: cancel visual
      await wrapper.find(".lang-toggle-btn").trigger("click");
      await nextTick();
      // Click 3: re-target PL — should await existing promise, not fire new one
      await wrapper.find(".lang-toggle-btn").trigger("click");
      await nextTick();
      expect(wrapper.find(".lang-flag").text()).toBe("🇵🇱");
      expect((wrapper.vm as any).translating).toBe(true);
      expect(translateTextsMock).toHaveBeenCalledTimes(1); // still only 1 request

      // Resolve — translation applies this time
      resolveTranslate({ translations: ["[translated]"] });
      await flushPromises();
      expect((wrapper.vm as any).currentLang).toBe("pl");
      expect(wrapper.emitted("translated")).toBeTruthy();
    });

    it("retries after an error on next click", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "en", confidence: 0.99 });

      translateTextsMock.mockRejectedValueOnce(new Error("boom"));

      const wrapper = mount(LanguageToggle, {
        props: { messages: makeMessages(["This is a long enough English message for detection."]) },
      });
      await flushPromises();
      await nextTick();

      await wrapper.find(".lang-toggle-btn").trigger("click");
      await flushPromises();
      expect((wrapper.vm as any).currentLang).toBe("en"); // unchanged — text never blanked
      expect((wrapper.vm as any).translating).toBe(false);

      // Second click issues a fresh request (errored promise was cleared)
      translateTextsMock.mockImplementation(async (texts: string[]) => ({
        translations: texts.map(t => `OK: ${t}`),
      }));
      await wrapper.find(".lang-toggle-btn").trigger("click");
      await flushPromises();
      expect((wrapper.vm as any).currentLang).toBe("pl");
      expect(wrapper.emitted("translated")).toBeTruthy();
    });
  });

  // ── Action labels in batch ──

  describe("action label batching", () => {
    it("sends [action:Label] labels as positional entries alongside their message text", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "en", confidence: 0.99 });
      translateTextsMock.mockImplementation(async (texts: string[]) => ({
        translations: texts.map(t => `PL:${t}`),
      }));

      const msg =
        "Your document is ready, choose an action: [action:Create diagram 📊] [action:Show metadata 📄]";
      const wrapper = mount(LanguageToggle, {
        props: { messages: [{ role: "assistant", content: msg }] },
      });
      await flushPromises();
      await nextTick();

      await wrapper.find(".lang-toggle-btn").trigger("click");
      await flushPromises();

      // One batch call should include: [stripped text, action label 1, action label 2]
      const batchCall = translateTextsMock.mock.calls.find(
        (args) => Array.isArray(args[0]) && (args[0] as string[]).length >= 3,
      );
      expect(batchCall).toBeTruthy();
      const sent = batchCall![0] as string[];
      expect(sent[1]).toBe("Create diagram 📊");
      expect(sent[2]).toBe("Show metadata 📄");
      // Main text slot must NOT contain the raw action fragments (opaque placeholder)
      expect(sent[0]).not.toContain("[action:");

      const translated = wrapper.emitted("translated")![0][0] as Map<number, string>;
      const out = translated.get(0)!;
      // Action labels restored in target language
      expect(out).toContain("[action:PL:Create diagram 📊]");
      expect(out).toContain("[action:PL:Show metadata 📄]");
    });
  });

  // ── Persisted translation per conversation + message ──

  describe("localStorage persistence", () => {
    beforeEach(() => {
      localStorage.clear();
    });

    it("loads persisted translation from localStorage on mount (no API call)", async () => {
      Object.defineProperty(navigator, "language", { value: "pl", configurable: true });
      detectLanguageMock.mockResolvedValue({ language: "en", confidence: 0.99 });

      // Pre-seed: conversation chose PL, and message m1 was translated to PL.
      localStorage.setItem(
        "conversation-languages",
        JSON.stringify({ convA: "pl" }),
      );
      localStorage.setItem("translation:pl:m1", "Wiadomość po polsku.");

      const wrapper = mount(LanguageToggle, {
        props: {
          messages: [
            { id: "m1", role: "assistant", content: "A message in English long enough to detect." },
          ],
          conversationId: "convA",
        },
      });
      await flushPromises();
      await nextTick();
      // Component defers auto-translate by 50ms (see watch in LanguageToggle.vue)
      // so downstream listeners get a chance to wire up before state changes.
      await new Promise(r => setTimeout(r, 80));
      await flushPromises();

      // The translation lived in localStorage, so no API call was needed.
      expect(translateTextsMock).not.toHaveBeenCalled();
      const translated = wrapper.emitted("translated")?.[0]?.[0] as Map<number, string> | undefined;
      expect(translated?.get(0)).toBe("Wiadomość po polsku.");
    });
  });
});
