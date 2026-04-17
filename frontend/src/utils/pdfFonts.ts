import jsPDF from "jspdf";

let fontsLoaded = false;
let fontRegularBase64 = "";
let fontBoldBase64 = "";
let fontItalicBase64 = "";

async function loadFontAsBase64(url: string): Promise<string> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to load font from ${url}: ${response.status}`);
  }
  const buffer = await response.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  // Sanity-check: TTF files start with 0x00010000
  if (bytes.length < 4 || !(bytes[0] === 0 && bytes[1] === 1 && bytes[2] === 0 && bytes[3] === 0)) {
    throw new Error(`Font file at ${url} is not a valid TTF`);
  }
  let binary = "";
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

export async function ensureFontsLoaded(): Promise<void> {
  if (fontsLoaded) return;
  const base = import.meta.env.BASE_URL || "/";
  const [regular, bold, italic] = await Promise.all([
    loadFontAsBase64(`${base}fonts/Roboto-Regular.ttf`),
    loadFontAsBase64(`${base}fonts/Roboto-Bold.ttf`),
    loadFontAsBase64(`${base}fonts/Roboto-Italic.ttf`),
  ]);
  fontRegularBase64 = regular;
  fontBoldBase64 = bold;
  fontItalicBase64 = italic;
  fontsLoaded = true;
}

export function registerFonts(doc: jsPDF): void {
  if (!fontRegularBase64 || !fontBoldBase64 || !fontItalicBase64) {
    throw new Error("Fonts not loaded. Call ensureFontsLoaded() first.");
  }
  doc.addFileToVFS("Roboto-Regular.ttf", fontRegularBase64);
  doc.addFileToVFS("Roboto-Bold.ttf", fontBoldBase64);
  doc.addFileToVFS("Roboto-Italic.ttf", fontItalicBase64);
  doc.addFont("Roboto-Regular.ttf", "Roboto", "normal");
  doc.addFont("Roboto-Bold.ttf", "Roboto", "bold");
  doc.addFont("Roboto-Italic.ttf", "Roboto", "italic");
}

/** Font family name to use with doc.setFont() after registerFonts() */
export const PDF_FONT = "Roboto";
