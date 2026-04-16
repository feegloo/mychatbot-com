import html2canvas from "html2canvas-pro";
import jsPDF from "jspdf";

const PRINT_STYLES = `
  *, *::before, *::after { box-sizing: border-box; }
  body, .pdf-offscreen-container {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    color: #000;
    background: #fff;
    margin: 0;
    padding: 24px 32px;
    font-size: 13px;
    line-height: 1.6;
  }
  h1, h2, h3, h4, h5, h6 { color: #000; margin: 1em 0 0.5em; }
  h1 { font-size: 20px; }
  h2 { font-size: 17px; }
  h3 { font-size: 15px; }
  p { margin: 0.5em 0; }
  a { color: #000; text-decoration: underline; }
  table { border-collapse: collapse; width: 100%; margin: 12px 0; }
  th, td { border: 1px solid #444; padding: 6px 10px; text-align: left; font-size: 12px; }
  th { background: #f0f0f0; font-weight: 600; }
  .checklist-box {
    display: inline-block; width: 14px; height: 14px;
    border: 1.5px solid #333; border-radius: 2px;
    vertical-align: middle; margin-right: 6px; position: relative;
  }
  .checklist-box.checked::after {
    content: '✓'; position: absolute; top: -2px; left: 1px;
    font-size: 12px; font-weight: 700; color: #000;
  }
  pre { background: #f5f5f5; border: 1px solid #ddd; border-radius: 4px; padding: 10px; overflow-x: auto; font-size: 11px; }
  code { font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace; font-size: 11px; }
  p code, li code { background: #f0f0f0; padding: 1px 4px; border-radius: 3px; }
  ul, ol { padding-left: 24px; margin: 0.5em 0; }
  li { margin: 0.25em 0; }
  .quiz-block { border: 1px solid #ccc; border-radius: 8px; padding: 14px; margin: 14px 0; background: #fff; }
  .quiz-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; font-weight: 600; font-size: 15px; color: #000; }
  .quiz-download-btn { display: none; }
  .quiz-question { margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #eee; }
  .quiz-question:last-child { border-bottom: none; margin-bottom: 0; padding-bottom: 0; }
  .quiz-question-text { font-weight: 600; margin-bottom: 8px; font-size: 13px; }
  .quiz-option { display: flex; align-items: center; gap: 8px; padding: 5px 0; font-size: 12px; }
  .quiz-checkbox { display: none; }
  .quiz-checkbox-custom { width: 14px; height: 14px; border: 1.5px solid #333; border-radius: 2px; flex-shrink: 0; background: #fff; }
  .quiz-checkbox-custom::after { content: '' !important; }
  .quiz-variant-label { font-weight: 600; margin-right: 2px; }
  .quiz-option-text { flex: 1; }
  .quiz-explanation { display: none; }
  .quiz-summary { display: none; }
  .mermaid-block { border: 1px solid #ccc; border-radius: 8px; padding: 12px; margin: 12px 0; background: #fff; text-align: center; }
  .mermaid-toolbar { display: none; }
  .mermaid-diagram { display: flex; justify-content: center; }
  .mermaid-diagram svg { max-width: 100%; height: auto; }
  .mermaid-source, .mermaid-loading { display: none; }
  .inline-source-btn, .action-btn, .action-btns-row { display: none; }
  img { max-width: 100%; height: auto; }
`;

/**
 * Generates a PDF from the given HTML content and triggers a direct download.
 * Renders into a hidden off-screen container — no new browser window is opened.
 */
export async function printContentAsPdf(html: string, title: string) {
  // Create a hidden off-screen container styled for print
  const container = document.createElement("div");
  container.className = "pdf-offscreen-container";
  container.style.cssText =
    "position:fixed;left:-9999px;top:0;width:794px;background:#fff;z-index:-1;";

  const style = document.createElement("style");
  style.textContent = PRINT_STYLES;
  container.appendChild(style);

  const content = document.createElement("div");
  content.innerHTML = html;
  container.appendChild(content);

  document.body.appendChild(container);

  // Fix mermaid SVGs for print
  container.querySelectorAll("svg").forEach((svg) => {
    svg.style.maxWidth = "100%";
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

  try {
    await generateAndDownloadPdf(container, title);
  } finally {
    document.body.removeChild(container);
  }
}

async function generateAndDownloadPdf(sourceEl: HTMLElement, title: string) {
  try {
    const canvas = await html2canvas(sourceEl, {
      scale: 1,
      useCORS: true,
      backgroundColor: "#ffffff",
    });

    const imgWidth = canvas.width;
    const imgHeight = canvas.height;

    const pdf = new jsPDF({
      orientation: imgWidth > imgHeight ? "landscape" : "portrait",
      unit: "mm",
      format: "a4",
      compress: true,
    });

    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    const ratio = Math.min(pageWidth / imgWidth, pageHeight / imgHeight);
    const pdfImgWidth = imgWidth * ratio;

    let remainingHeight = imgHeight;
    let sourceY = 0;
    let isFirstPage = true;

    while (remainingHeight > 0) {
      if (!isFirstPage) pdf.addPage();
      isFirstPage = false;

      const sliceHeight = Math.min(remainingHeight, imgWidth * (pageHeight / pdfImgWidth));
      const sliceCanvas = document.createElement("canvas");
      sliceCanvas.width = imgWidth;
      sliceCanvas.height = sliceHeight;
      const ctx = sliceCanvas.getContext("2d")!;
      ctx.drawImage(canvas, 0, sourceY, imgWidth, sliceHeight, 0, 0, imgWidth, sliceHeight);

      const sliceData = sliceCanvas.toDataURL("image/jpeg", 0.5);
      const slicePdfHeight = sliceHeight * ratio;
      pdf.addImage(sliceData, "JPEG", 0, 0, pdfImgWidth, slicePdfHeight);

      sourceY += sliceHeight;
      remainingHeight -= sliceHeight;
    }

    const safeName = title
      .replace(/[^a-zA-Z0-9\u0080-\uFFFF _-]+/g, "_")
      .replace(/_+/g, "_")
      .slice(0, 100);
    pdf.save(`${safeName}.pdf`);
  } catch (e) {
    console.error("PDF download failed:", e);
  }
}

function escapeHtml(str: string): string {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
