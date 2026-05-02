import { describe, it, expect } from "vitest";
import {
  buildSentenceChunkSizes,
  buildSynthesisChunks,
  cleanTextForTTS,
  extractPoemOrQuoteForAutoRead,
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

  it("removes mermaid code blocks", () => {
    const input = "Here is a diagram:\n\n```mermaid\ngraph TD\n  A-->B\n  B-->C\n```\n\nAs shown above.";
    expect(cleanTextForTTS(input)).toBe("Here is a diagram: As shown above.");
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

  it("removes poem blocks keeping verse content", () => {
    expect(cleanTextForTTS("[poem]\nRoses are red.\nViolets are blue.\n[/poem]")).toBe(
      "Roses are red. Violets are blue.",
    );
  });

  it("removes quote blocks keeping quote content", () => {
    expect(cleanTextForTTS("[quote]\nBe the change.\n[/quote]")).toBe(
      "Be the change.",
    );
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

describe("extractPoemOrQuoteForAutoRead", () => {
  it("returns poem body when poem block exists", () => {
    expect(
      extractPoemOrQuoteForAutoRead(
        "Intro text [poem]\nLine one\nLine two\n[/poem]\nTrailing text",
      ),
    ).toBe("Line one\nLine two");
  });

  it("returns null when no poem or quote block exists", () => {
    expect(extractPoemOrQuoteForAutoRead("Plain answer without poem block.")).toBeNull();
  });

  it("trims leading blank lines inside poem block", () => {
    expect(extractPoemOrQuoteForAutoRead("[poem]\n  \n  Line one\n[/poem]")).toBe(
      "Line one",
    );
  });

  it("returns quote body when quote block exists", () => {
    expect(
      extractPoemOrQuoteForAutoRead(
        "Intro text [quote]\nBe the change.\n— Gandhi\n[/quote]\nTrailing text",
      ),
    ).toBe("Be the change.\n— Gandhi");
  });

  it("prefers poem over quote when both are present", () => {
    expect(
      extractPoemOrQuoteForAutoRead("[poem]\nVerse\n[/poem] [quote]\nAphorism\n[/quote]"),
    ).toBe("Verse");
  });
});

describe("buildSentenceChunkSizes", () => {
  it("builds 1,2,4 progression and merges a smaller remainder", () => {
    expect(buildSentenceChunkSizes(9)).toEqual([1, 2, 6]);
  });

  it("keeps regular powers-of-two progression when exact", () => {
    expect(buildSentenceChunkSizes(7)).toEqual([1, 2, 4]);
  });

  it("does not merge when the final chunk is not smaller", () => {
    expect(buildSentenceChunkSizes(15)).toEqual([1, 2, 4, 8]);
  });
});

describe("buildSynthesisChunks", () => {
  it("splits sentence array using async chunk progression", () => {
    const sentences = [
      "S1.",
      "S2.",
      "S3.",
      "S4.",
      "S5.",
      "S6.",
      "S7.",
      "S8.",
      "S9.",
    ];
    expect(buildSynthesisChunks(sentences)).toEqual([
      "S1.",
      "S2. S3.",
      "S4. S5. S6. S7. S8. S9.",
    ]);
  });

  it("splits overlong chunk text to satisfy max chunk length", () => {
    const longWord = "a".repeat(5000);
    const chunks = buildSynthesisChunks([longWord]);
    expect(chunks).toHaveLength(2);
    expect(chunks.every((chunk) => chunk.length <= 4096)).toBe(true);
    expect(chunks.join("")).toBe(longWord);
  });
});
