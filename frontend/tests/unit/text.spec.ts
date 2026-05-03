import { describe, it, expect } from "vitest";
import { cleanFileName, isUrl, linkify } from "../../src/utils/text";

describe("cleanFileName", () => {
  it("strips UUID prefix from filename (legacy format)", () => {
    expect(cleanFileName("550e8400-e29b-41d4-a716-446655440000_report.pdf")).toBe("report.pdf");
  });

  it("strips short-ID suffix from filename (new format)", () => {
    expect(cleanFileName("report_Abc123XYZdef4567.pdf")).toBe("report.pdf");
  });

  it("returns name unchanged if no UUID prefix or short-ID suffix", () => {
    expect(cleanFileName("report.pdf")).toBe("report.pdf");
  });

  it("handles empty string", () => {
    expect(cleanFileName("")).toBe("");
  });

  it("only strips the first UUID prefix (legacy)", () => {
    expect(cleanFileName("550e8400-e29b-41d4-a716-446655440000_550e8400-e29b-41d4-a716-446655440001_file.txt"))
      .toBe("550e8400-e29b-41d4-a716-446655440001_file.txt");
  });

  it("strips short-ID suffix from filename without extension", () => {
    expect(cleanFileName("Wallhaven-289e1g_B2p2jEVxhjrYZkvh")).toBe("Wallhaven-289e1g");
  });
});

describe("linkify", () => {
  it("converts HTTP URLs to links", () => {
    const result = linkify("Visit https://example.com for info");
    expect(result).toContain('<a href="https://example.com"');
    expect(result).toContain("https://example.com");
  });

  it("converts bare domains to HTTPS links", () => {
    const result = linkify("Visit example.com for info");
    expect(result).toContain('<a href="https://example.com"');
  });

  it("converts email addresses to mailto links", () => {
    const result = linkify("Contact user@example.com");
    expect(result).toContain('<a href="mailto:user@example.com"');
  });

  it("escapes HTML entities", () => {
    const result = linkify("<script>alert('xss')</script>");
    expect(result).not.toContain("<script>");
    expect(result).toContain("&lt;script&gt;");
  });

  it("returns plain text unchanged when no URLs", () => {
    const result = linkify("Hello world");
    expect(result).toBe("Hello world");
  });
});

describe("isUrl", () => {
  it("returns true for valid http URL", () => {
    expect(isUrl("http://example.com")).toBe(true);
  });

  it("returns true for valid https URL with path and query", () => {
    expect(isUrl("https://allegro.pl/produkt/foo-bar?id=123#section")).toBe(true);
  });

  it("returns true when surrounded by whitespace (trimmed internally)", () => {
    expect(isUrl("  https://example.com  ")).toBe(true);
  });

  it("returns false for plain text", () => {
    expect(isUrl("hello world")).toBe(false);
  });

  it("returns false for text containing a URL with spaces", () => {
    expect(isUrl("check out https://example.com for more")).toBe(false);
  });

  it("returns false for empty string", () => {
    expect(isUrl("")).toBe(false);
  });

  it("returns false for ftp URL (not http/https)", () => {
    expect(isUrl("ftp://example.com")).toBe(false);
  });
});
