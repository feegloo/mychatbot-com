/**
 * Opens a print-friendly window with the given HTML content,
 * styled for clean black-on-white PDF output via the browser's Save as PDF.
 */
export function printContentAsPdf(html: string, title: string) {
  const printWindow = window.open("", "_blank");
  if (!printWindow) return;

  printWindow.document.write(`<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>${escapeHtml(title)}</title>
<style>
  *, *::before, *::after { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    color: #000;
    background: #fff;
    margin: 0;
    padding: 24px 32px;
    font-size: 13px;
    line-height: 1.6;
  }
  h1, h2, h3, h4, h5, h6 { color: #000; margin: 1em 0 0.5em; page-break-after: avoid; }
  h1 { font-size: 20px; }
  h2 { font-size: 17px; }
  h3 { font-size: 15px; }
  p { margin: 0.5em 0; }
  a { color: #000; text-decoration: underline; }

  /* Tables */
  table { border-collapse: collapse; width: 100%; margin: 12px 0; page-break-inside: auto; }
  tr { page-break-inside: avoid; }
  th, td { border: 1px solid #444; padding: 6px 10px; text-align: left; font-size: 12px; }
  th { background: #f0f0f0; font-weight: 600; }

  /* Checklists */
  .checklist-box {
    display: inline-block;
    width: 14px;
    height: 14px;
    border: 1.5px solid #333;
    border-radius: 2px;
    vertical-align: middle;
    margin-right: 6px;
    position: relative;
  }
  .checklist-box.checked::after {
    content: '✓';
    position: absolute;
    top: -2px;
    left: 1px;
    font-size: 12px;
    font-weight: 700;
    color: #000;
  }

  /* Code blocks */
  pre { background: #f5f5f5; border: 1px solid #ddd; border-radius: 4px; padding: 10px; overflow-x: auto; font-size: 11px; page-break-inside: avoid; }
  code { font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace; font-size: 11px; }
  p code, li code { background: #f0f0f0; padding: 1px 4px; border-radius: 3px; }

  /* Lists */
  ul, ol { padding-left: 24px; margin: 0.5em 0; }
  li { margin: 0.25em 0; }

  /* Quiz blocks */
  .quiz-block { border: 1px solid #ccc; border-radius: 8px; padding: 14px; margin: 14px 0; background: #fff; }
  .quiz-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; font-weight: 600; font-size: 15px; color: #000; }
  .quiz-header svg { stroke: #000; }
  .quiz-download-btn { display: none; }
  .quiz-question { margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #eee; }
  .quiz-question:last-child { border-bottom: none; margin-bottom: 0; padding-bottom: 0; }
  .quiz-question-text { font-weight: 600; margin-bottom: 8px; font-size: 13px; }
  .quiz-option { display: flex; align-items: center; gap: 8px; padding: 5px 0; font-size: 12px; }
  .quiz-checkbox { display: none; }
  .quiz-checkbox-custom {
    width: 14px; height: 14px; border: 1.5px solid #333; border-radius: 2px;
    flex-shrink: 0; background: #fff;
  }
  .quiz-checkbox-custom::after { content: '' !important; }
  .quiz-variant-label { font-weight: 600; margin-right: 2px; }
  .quiz-option-text { flex: 1; }
  .quiz-explanation { display: none; }
  .quiz-summary { display: none; }

  /* Mermaid diagrams */
  .mermaid-block { border: 1px solid #ccc; border-radius: 8px; padding: 12px; margin: 12px 0; background: #fff; text-align: center; }
  .mermaid-toolbar { display: none; }
  .mermaid-diagram { display: flex; justify-content: center; }
  .mermaid-diagram svg { max-width: 100%; height: auto; }
  .mermaid-source { display: none; }
  .mermaid-loading { display: none; }

  /* Hide interactive elements */
  .inline-source-btn { display: none; }
  .action-btn { display: none; }
  .action-btns-row { display: none; }

  /* Images */
  img { max-width: 100%; height: auto; }

  /* Print-specific */
  @media print {
    body { padding: 0; }
  }
</style>
</head>
<body>${html}</body>
</html>`);
  printWindow.document.close();

  // Fix mermaid SVGs: remove dark theme inline styles
  const svgs = printWindow.document.querySelectorAll("svg");
  svgs.forEach((svg) => {
    svg.style.maxWidth = "100%";
    // Recolor text elements to black for print
    svg.querySelectorAll("text, tspan").forEach((el) => {
      (el as HTMLElement).style.fill = "#000";
    });
    svg.querySelectorAll("[stroke]").forEach((el) => {
      const s = el.getAttribute("stroke");
      if (s && s !== "none" && s !== "transparent") {
        el.setAttribute("stroke", "#333");
      }
    });
  });

}

function escapeHtml(str: string): string {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
