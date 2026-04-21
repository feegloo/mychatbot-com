import { describe, it, expect } from "vitest";
import { renderInlineMarkdown, renderMarkdown } from "../../src/utils/markdown";

describe("renderMarkdown table wrapping", () => {
  it("wraps markdown tables in a horizontal scroll container", () => {
    const html = renderMarkdown("| Col A | Col B |\n| --- | --- |\n| A1 | B1 |");

    expect(html).toContain('<div class="markdown-table-scroll"><table>');
    expect(html).toContain("</table></div>");
  });

  it("preserves table attributes when wrapping html tables", () => {
    const html = renderMarkdown('<table class="wide-table"><tr><td>Cell</td></tr></table>');

    expect(html).toContain('<div class="markdown-table-scroll"><table class="wide-table">');
  });

  it("does not add table wrapper when no table exists", () => {
    const html = renderMarkdown("Plain paragraph without table.");

    expect(html).not.toContain("markdown-table-scroll");
  });

  it("wraps markdown images in a horizontal scroll container", () => {
    const html = renderMarkdown("![Generated chart](https://example.com/chart.png)");

    expect(html).toContain('<span class="markdown-image-scroll"><img');
    expect(html).toContain('src="https://example.com/chart.png"');
    expect(html).toContain('alt="Generated chart"');
  });

  it("renders supported color markers", () => {
    const html = renderMarkdown(
      "[c:yellow]warning[/c] [c:gold]highlight[/c] [c:gray]neutral[/c]",
    );

    expect(html).toContain('<span class="text-color-yellow">warning</span>');
    expect(html).toContain('<span class="text-color-gold">highlight</span>');
    expect(html).toContain('<span class="text-color-gray">neutral</span>');
  });

  it("strips unsupported color markers while keeping text", () => {
    const html = renderMarkdown("[c:brown]value[/c]");

    expect(html).toContain("value");
    expect(html).not.toContain("text-color-brown");
  });
});

describe("renderInlineMarkdown", () => {
  it("renders italic and bold markdown", () => {
    const html = renderInlineMarkdown("What made _The Alchemist_ **famous**?");

    expect(html).toContain("<em>The Alchemist</em>");
    expect(html).toContain("<strong>famous</strong>");
  });

  it("renders links with safe target attributes", () => {
    const html = renderInlineMarkdown("[Open docs](https://example.com/docs)");

    expect(html).toContain('href="https://example.com/docs"');
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer"');
  });
});
