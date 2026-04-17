import jsPDF from "jspdf";
import { ensureFontsLoaded, registerFonts, PDF_FONT } from "./pdfFonts";

/**
 * Generates a PDF from raw markdown content using native jsPDF text rendering.
 * No html2canvas / DOM screenshot — instant, no blink, clean vector text output.
 */
export async function printContentAsPdf(markdown: string, title: string) {
  await ensureFontsLoaded();
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  registerFonts(doc);
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const marginLeft = 20;
  const marginRight = 20;
  const marginBottom = 20;
  const contentWidth = pageWidth - marginLeft - marginRight;
  let y = 20;

  const checkNewPage = (needed: number) => {
    if (y + needed > pageHeight - marginBottom) {
      doc.addPage();
      y = 20;
    }
  };

  // Strip source citations [source:N], action markers [action:...], and mermaid blocks
  const cleaned = markdown
    .replace(/\[source:\s*\d+(?:,\s*\d+)*\]/g, "")
    .replace(/\[action:\s*[^\]]+\]/g, "")
    .replace(/```mermaid[\s\S]*?```/g, "[Diagram]");

  const lines = cleaned.split("\n");
  let i = 0;
  let inCodeBlock = false;

  while (i < lines.length) {
    const line = lines[i];

    // --- Code blocks ---
    if (line.trimStart().startsWith("```")) {
      if (!inCodeBlock) {
        inCodeBlock = true;
        i++;
        continue;
      } else {
        inCodeBlock = false;
        y += 2;
        i++;
        continue;
      }
    }

    if (inCodeBlock) {
      checkNewPage(5);
      doc.setFont(PDF_FONT, "normal");
      doc.setFontSize(9);
      doc.setTextColor(60, 60, 60);
      const codeLines = doc.splitTextToSize(line || " ", contentWidth - 8);
      // Draw code background
      const blockH = codeLines.length * 4 + 2;
      checkNewPage(blockH);
      doc.setFillColor(245, 245, 245);
      doc.setDrawColor(220, 220, 220);
      doc.roundedRect(marginLeft, y - 3, contentWidth, blockH, 1, 1, "FD");
      doc.text(codeLines, marginLeft + 4, y);
      y += blockH + 1;
      i++;
      continue;
    }

    // --- Blank lines ---
    if (line.trim() === "") {
      y += 3;
      i++;
      continue;
    }

    // --- Horizontal rule ---
    if (/^(\s*[-*_]){3,}\s*$/.test(line)) {
      checkNewPage(6);
      doc.setDrawColor(180, 180, 180);
      doc.setLineWidth(0.3);
      doc.line(marginLeft, y, pageWidth - marginRight, y);
      y += 6;
      i++;
      continue;
    }

    // --- Headings ---
    const headingMatch = line.match(/^(#{1,6})\s+(.*)/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const text = stripInlineFormatting(headingMatch[2]);
      const sizes: Record<number, number> = { 1: 18, 2: 15, 3: 13, 4: 12, 5: 11, 6: 10.5 };
      const fontSize = sizes[level] || 11;
      const spacing = level <= 2 ? 8 : 5;

      y += spacing;
      checkNewPage(fontSize / 2 + 4);
      doc.setFont(PDF_FONT, "bold");
      doc.setFontSize(fontSize);
      doc.setTextColor(0, 0, 0);
      const wrapped = doc.splitTextToSize(text, contentWidth);
      doc.text(wrapped, marginLeft, y);
      y += wrapped.length * (fontSize * 0.4) + 3;
      i++;
      continue;
    }

    // --- Tables ---
    if (line.includes("|") && line.trim().startsWith("|")) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim().startsWith("|")) {
        tableLines.push(lines[i]);
        i++;
      }
      renderTable(doc, tableLines, marginLeft, contentWidth, y, checkNewPage);
      // Estimate height: each row ~6mm
      const dataRows = tableLines.filter((l) => !/^[\s|:-]+$/.test(l));
      y += dataRows.length * 6 + 4;
      continue;
    }

    // --- Checklists ---
    const checklistMatch = line.match(/^(\s*)[-*+]\s+\[([ xX])\]\s+(.*)/);
    if (checklistMatch) {
      const checked = checklistMatch[2].toLowerCase() === "x";
      const text = stripInlineFormatting(checklistMatch[3]);
      checkNewPage(6);
      doc.setFont(PDF_FONT, "normal");
      doc.setFontSize(10.5);
      doc.setTextColor(0, 0, 0);
      // Draw checkbox
      const boxX = marginLeft + 2;
      const boxY = y - 3;
      doc.setDrawColor(100, 100, 100);
      doc.setLineWidth(0.4);
      doc.rect(boxX, boxY, 3.5, 3.5);
      if (checked) {
        doc.setFont(PDF_FONT, "bold");
        doc.text("✓", boxX + 0.5, boxY + 3);
        doc.setFont(PDF_FONT, "normal");
      }
      const wrapped = doc.splitTextToSize(text, contentWidth - 12);
      doc.text(wrapped, marginLeft + 9, y);
      y += wrapped.length * 4.5 + 2;
      i++;
      continue;
    }

    // --- Unordered list items ---
    const ulMatch = line.match(/^(\s*)[-*+]\s+(.*)/);
    if (ulMatch) {
      const indent = Math.min(Math.floor(ulMatch[1].length / 2), 3);
      const text = stripInlineFormatting(ulMatch[2]);
      checkNewPage(6);
      doc.setFont(PDF_FONT, "normal");
      doc.setFontSize(10.5);
      doc.setTextColor(0, 0, 0);
      const bulletX = marginLeft + indent * 5;
      doc.text("•", bulletX, y);
      const wrapped = doc.splitTextToSize(text, contentWidth - (indent * 5) - 5);
      doc.text(wrapped, bulletX + 4, y);
      y += wrapped.length * 4.5 + 2;
      i++;
      continue;
    }

    // --- Ordered list items ---
    const olMatch = line.match(/^(\s*)(\d+)[.)]\s+(.*)/);
    if (olMatch) {
      const indent = Math.min(Math.floor(olMatch[1].length / 2), 3);
      const num = olMatch[2];
      const text = stripInlineFormatting(olMatch[3]);
      checkNewPage(6);
      doc.setFont(PDF_FONT, "normal");
      doc.setFontSize(10.5);
      doc.setTextColor(0, 0, 0);
      const numX = marginLeft + indent * 5;
      doc.text(`${num}.`, numX, y);
      const wrapped = doc.splitTextToSize(text, contentWidth - (indent * 5) - 7);
      doc.text(wrapped, numX + 6, y);
      y += wrapped.length * 4.5 + 2;
      i++;
      continue;
    }

    // --- Regular paragraph ---
    const text = stripInlineFormatting(line);
    checkNewPage(6);
    doc.setFont(PDF_FONT, "normal");
    doc.setFontSize(10.5);
    doc.setTextColor(0, 0, 0);

    // Collect continuation lines (non-blank, non-special)
    let paragraph = text;
    while (
      i + 1 < lines.length &&
      lines[i + 1].trim() !== "" &&
      !lines[i + 1].trimStart().startsWith("#") &&
      !lines[i + 1].trimStart().startsWith("```") &&
      !lines[i + 1].trimStart().match(/^[-*+]\s/) &&
      !lines[i + 1].trimStart().match(/^\d+[.)]\s/) &&
      !(lines[i + 1].includes("|") && lines[i + 1].trim().startsWith("|")) &&
      !/^(\s*[-*_]){3,}\s*$/.test(lines[i + 1])
    ) {
      i++;
      paragraph += " " + stripInlineFormatting(lines[i]);
    }

    const wrapped = doc.splitTextToSize(paragraph, contentWidth);
    for (const wline of wrapped) {
      checkNewPage(5);
      doc.text(wline, marginLeft, y);
      y += 4.5;
    }
    y += 2;
    i++;
  }

  const safeName = title
    .replace(/[^a-zA-Z0-9\u0080-\uFFFF _-]+/g, "_")
    .replace(/_+/g, "_")
    .slice(0, 100);
  doc.save(`${safeName}.pdf`);
}

/** Strip markdown inline formatting (bold, italic, code, links) to plain text */
function stripInlineFormatting(text: string): string {
  return text
    .replace(/\*\*\*(.+?)\*\*\*/g, "$1")   // bold+italic
    .replace(/\*\*(.+?)\*\*/g, "$1")         // bold
    .replace(/__(.+?)__/g, "$1")              // bold alt
    .replace(/\*(.+?)\*/g, "$1")              // italic
    .replace(/_(.+?)_/g, "$1")                // italic alt
    .replace(/~~(.+?)~~/g, "$1")              // strikethrough
    .replace(/`([^`]+)`/g, "$1")              // inline code
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")  // links → text only
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1 [image]") // images
    .trim();
}

/** Render a markdown table using jsPDF drawing primitives */
function renderTable(
  doc: jsPDF,
  tableLines: string[],
  marginLeft: number,
  contentWidth: number,
  startY: number,
  checkNewPage: (needed: number) => void,
) {
  // Parse table rows (skip separator line)
  const rows: string[][] = [];
  let isHeader = true;
  for (const line of tableLines) {
    const trimmed = line.trim().replace(/^\||\|$/g, "");
    if (/^[\s|:-]+$/.test(trimmed)) continue; // separator
    const cells = trimmed.split("|").map((c) => stripInlineFormatting(c.trim()));
    rows.push(cells);
  }
  if (rows.length === 0) return;

  const colCount = Math.max(...rows.map((r) => r.length));
  const colWidth = contentWidth / colCount;
  const rowHeight = 6;
  let y = startY;

  for (let ri = 0; ri < rows.length; ri++) {
    checkNewPage(rowHeight + 2);
    const row = rows[ri];
    const isHeaderRow = ri === 0 && isHeader;

    if (isHeaderRow) {
      doc.setFillColor(240, 240, 240);
      doc.rect(marginLeft, y - 4, contentWidth, rowHeight, "F");
    }

    doc.setDrawColor(160, 160, 160);
    doc.setLineWidth(0.2);
    doc.rect(marginLeft, y - 4, contentWidth, rowHeight);

    doc.setFont(PDF_FONT, isHeaderRow ? "bold" : "normal");
    doc.setFontSize(9.5);
    doc.setTextColor(0, 0, 0);

    for (let ci = 0; ci < colCount; ci++) {
      const cellText = row[ci] || "";
      const x = marginLeft + ci * colWidth + 2;
      // Draw cell border
      if (ci > 0) {
        doc.line(marginLeft + ci * colWidth, y - 4, marginLeft + ci * colWidth, y - 4 + rowHeight);
      }
      const clipped = doc.splitTextToSize(cellText, colWidth - 4);
      doc.text(clipped[0] || "", x, y);
    }
    y += rowHeight;
  }
}
