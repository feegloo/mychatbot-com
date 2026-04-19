import { describe, it, expect } from "vitest";
import {
  cleanTextForTTS,
  splitIntoSentences,
} from "../../src/composables/useAutoRead";

describe("cleanTextForTTS", () => {
  it("removes [source:N] markers", () => {
    expect(cleanTextForTTS("Hello [source:1] world [source:2,3]")).toBe(
      "Hello world",
    );
  });

  it("removes bare [N] citation references", () => {
    expect(cleanTextForTTS("Point one [1] and two [2,3]")).toBe(
      "Point one and two",
    );
  });

  it("removes [action:Label] markers", () => {
    expect(
      cleanTextForTTS("Answer text [action:Learn more about this topic]"),
    ).toBe("Answer text");
  });

  it("strips [c:color]...[/c] keeping inner text", () => {
    expect(cleanTextForTTS("[c:green]important[/c] text")).toBe(
      "important text",
    );
  });

  it("strips [poem]...[/poem] keeping inner text", () => {
    expect(cleanTextForTTS("[poem]\nRoses are red\n[/poem]")).toBe(
      "Roses are red",
    );
  });

  it("removes [quiz:...] blocks", () => {
    expect(
      cleanTextForTTS('Before [quiz:{"title":"Test"}] after'),
    ).toBe("Before after");
  });

  it("removes markdown images", () => {
    expect(cleanTextForTTS("See ![alt](http://img.png) here")).toBe(
      "See here",
    );
  });

  it("removes HTML tags", () => {
    expect(cleanTextForTTS("Hello <b>bold</b> world")).toBe(
      "Hello bold world",
    );
  });

  it("removes markdown header markers", () => {
    expect(cleanTextForTTS("## Section Title\nContent")).toBe(
      "Section Title Content",
    );
  });

  it("removes markdown bold/italic markers", () => {
    expect(cleanTextForTTS("This is **bold** and *italic*")).toBe(
      "This is bold and italic",
    );
  });

  it("removes markdown links keeping text", () => {
    expect(cleanTextForTTS("Click [here](http://example.com)")).toBe(
      "Click here",
    );
  });

  it("removes emojis", () => {
    const result = cleanTextForTTS("Hello 🎉 world 🔥");
    expect(result).not.toContain("🎉");
    expect(result).not.toContain("🔥");
  });

  it("removes ⚠️ marker", () => {
    expect(cleanTextForTTS("⚠️ Error occurred")).toBe("Error occurred");
  });

  it("collapses extra whitespace", () => {
    expect(cleanTextForTTS("Hello   \n\n   world")).toBe("Hello world");
  });

  it("handles complex mixed content", () => {
    const input =
      "## Stage 1: **Haemostasis** 🩸\n\nThis starts [source:8] within seconds. [action:Learn more about healing]\n\n[quiz:{\"title\":\"test\"}]";
    const result = cleanTextForTTS(input);
    expect(result).not.toContain("[source:");
    expect(result).not.toContain("[action:");
    expect(result).not.toContain("[quiz:");
    expect(result).not.toContain("##");
    expect(result).not.toContain("**");
    expect(result).toContain("Stage 1:");
    expect(result).toContain("Haemostasis");
    expect(result).toContain("This starts within seconds.");
  });
});

describe("splitIntoSentences", () => {
  it("returns single sentence as-is", () => {
    expect(splitIntoSentences("Hello world.")).toEqual(["Hello world."]);
  });

  it("splits on periods", () => {
    expect(splitIntoSentences("First. Second. Third.")).toEqual([
      "First.",
      "Second.",
      "Third.",
    ]);
  });

  it("splits on exclamation and question marks", () => {
    expect(splitIntoSentences("Really? Yes! Done.")).toEqual([
      "Really?",
      "Yes!",
      "Done.",
    ]);
  });

  it("handles text without terminal punctuation", () => {
    expect(splitIntoSentences("No ending punctuation")).toEqual([
      "No ending punctuation",
    ]);
  });

  it("returns empty array for empty text", () => {
    expect(splitIntoSentences("")).toEqual([]);
  });

  it("handles whitespace-only text", () => {
    expect(splitIntoSentences("   ")).toEqual([]);
  });

  it("handles multi-sentence paragraph", () => {
    const text =
      "Stage 1 starts within seconds. Stage 2 follows quickly. Stage 3 takes longer. Stage 4 is rebuilding. Stage 5 is maturation.";
    const sentences = splitIntoSentences(text);
    expect(sentences).toHaveLength(5);
    expect(sentences[0]).toBe("Stage 1 starts within seconds.");
    expect(sentences[4]).toBe("Stage 5 is maturation.");
  });
});
