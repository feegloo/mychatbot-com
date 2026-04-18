import { describe, it, expect, vi, beforeEach } from 'vitest';
import jsPDF from 'jspdf';

// Reset module state between tests by using dynamic imports
describe('pdfFonts', () => {
  const fakeBase64 = 'AAAA'; // minimal valid base64

  beforeEach(() => {
    vi.restoreAllMocks();
    // Mock fetch to return fake font data with valid TTF magic bytes (0x00010000)
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      arrayBuffer: () => Promise.resolve(new Uint8Array([0, 1, 0, 0]).buffer),
    } as unknown as Response);
  });

  it('ensureFontsLoaded fetches both font files', async () => {
    // Fresh import to reset module state
    vi.resetModules();
    const { ensureFontsLoaded } = await import('../../src/utils/pdfFonts');

    await ensureFontsLoaded();

    expect(globalThis.fetch).toHaveBeenCalledTimes(3);
    const urls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c: unknown[]) => c[0] as string);
    expect(urls.some((u: string) => u.includes('Roboto-Regular.ttf'))).toBe(true);
    expect(urls.some((u: string) => u.includes('Roboto-Bold.ttf'))).toBe(true);
    expect(urls.some((u: string) => u.includes('Roboto-Italic.ttf'))).toBe(true);
  });

  it('ensureFontsLoaded caches and does not re-fetch', async () => {
    vi.resetModules();
    const { ensureFontsLoaded } = await import('../../src/utils/pdfFonts');

    await ensureFontsLoaded();
    await ensureFontsLoaded();

    // Only fetched once (3 files on first call, 0 on second)
    expect(globalThis.fetch).toHaveBeenCalledTimes(3);
  });

  it('registerFonts adds fonts to jsPDF instance', async () => {
    vi.resetModules();
    const { ensureFontsLoaded, registerFonts } = await import('../../src/utils/pdfFonts');

    await ensureFontsLoaded();

    const doc = new jsPDF();
    const addFileToVFSSpy = vi.spyOn(doc, 'addFileToVFS');
    const addFontSpy = vi.spyOn(doc, 'addFont');

    registerFonts(doc);

    expect(addFileToVFSSpy).toHaveBeenCalledTimes(3);
    expect(addFileToVFSSpy).toHaveBeenCalledWith('Roboto-Regular.ttf', expect.any(String));
    expect(addFileToVFSSpy).toHaveBeenCalledWith('Roboto-Bold.ttf', expect.any(String));
    expect(addFileToVFSSpy).toHaveBeenCalledWith('Roboto-Italic.ttf', expect.any(String));
    expect(addFontSpy).toHaveBeenCalledWith('Roboto-Regular.ttf', 'Roboto', 'normal');
    expect(addFontSpy).toHaveBeenCalledWith('Roboto-Bold.ttf', 'Roboto', 'bold');
    expect(addFontSpy).toHaveBeenCalledWith('Roboto-Italic.ttf', 'Roboto', 'italic');
  });

  it('registerFonts throws if fonts not loaded', async () => {
    vi.resetModules();
    const { registerFonts } = await import('../../src/utils/pdfFonts');

    const doc = new jsPDF();
    expect(() => registerFonts(doc)).toThrow('Fonts not loaded');
  });

  it('PDF_FONT equals Roboto', async () => {
    vi.resetModules();
    const { PDF_FONT } = await import('../../src/utils/pdfFonts');
    expect(PDF_FONT).toBe('Roboto');
  });
});
