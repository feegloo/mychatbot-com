import { describe, it, expect } from "vitest";
import { renderMarkdown } from "../../src/utils/markdown";

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
});
