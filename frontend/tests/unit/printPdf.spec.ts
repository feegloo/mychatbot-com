import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Mock pdfFonts so tests don't need real font files ──
vi.mock('../../src/utils/pdfFonts', () => ({
  ensureFontsLoaded: vi.fn().mockResolvedValue(undefined),
  registerFonts: vi.fn(),
  PDF_FONT: 'Roboto',
}));

// ── Track all jsPDF instance method calls via a mock constructor ──
let mockDoc: Record<string, ReturnType<typeof vi.fn>>;

vi.mock('jspdf', () => {
  const MockJsPDF = function (this: any) {
    // Each instance gets fresh spies that delegate to the shared mockDoc
    Object.assign(this, mockDoc);
    this.internal = {
      pageSize: { getWidth: () => 210, getHeight: () => 297 },
    };
  } as any;
  MockJsPDF.prototype = {};
  return { default: MockJsPDF, jsPDF: MockJsPDF };
});

import { printContentAsPdf } from '../../src/utils/printPdf';
import { ensureFontsLoaded, registerFonts } from '../../src/utils/pdfFonts';

beforeEach(() => {
  vi.clearAllMocks();
  mockDoc = {
    setFont: vi.fn(),
    setFontSize: vi.fn(),
    setTextColor: vi.fn(),
    setDrawColor: vi.fn(),
    setFillColor: vi.fn(),
    setLineWidth: vi.fn(),
    text: vi.fn(),
    line: vi.fn(),
    rect: vi.fn(),
    roundedRect: vi.fn(),
    addPage: vi.fn(),
    save: vi.fn(),
    splitTextToSize: vi.fn().mockImplementation((text: string, _width: number) => [text]),
  };
});

function allTextStrings(): string[] {
  return mockDoc.text.mock.calls.map(([t]: [unknown]) =>
    Array.isArray(t) ? t.join(' ') : String(t),
  );
}

describe('printContentAsPdf', () => {
  it('loads fonts and registers them on the doc', async () => {
    await printContentAsPdf('Hello world', 'test');

    expect(ensureFontsLoaded).toHaveBeenCalledOnce();
    expect(registerFonts).toHaveBeenCalledOnce();
  });

  it('saves with sanitised filename', async () => {
    await printContentAsPdf('content', 'Cześć! / hello <world>');

    expect(mockDoc.save).toHaveBeenCalledOnce();
    const filename: string = mockDoc.save.mock.calls[0][0];
    expect(filename).toMatch(/\.pdf$/);
    // Should not contain filesystem-unsafe characters
    expect(filename).not.toMatch(/[/<>]/);
  });

  it('renders headings', async () => {
    await printContentAsPdf('# Main Title\n\nSome paragraph', 'test');

    const texts = allTextStrings();
    expect(texts.some((t) => t.includes('Main Title'))).toBe(true);
    expect(texts.some((t) => t.includes('Some paragraph'))).toBe(true);
  });

  it('renders unordered list items with bullet', async () => {
    await printContentAsPdf('- Item one\n- Item two', 'test');

    const texts = allTextStrings();
    expect(texts.some((t) => t === '•')).toBe(true);
    expect(texts.some((t) => t.includes('Item one'))).toBe(true);
    expect(texts.some((t) => t.includes('Item two'))).toBe(true);
  });

  it('renders ordered list items', async () => {
    await printContentAsPdf('1. First\n2. Second', 'test');

    const texts = allTextStrings();
    expect(texts.some((t) => t === '1.')).toBe(true);
    expect(texts.some((t) => t === '2.')).toBe(true);
  });

  it('handles code blocks', async () => {
    const md = '```js\nconsole.log("hi")\n```';
    await printContentAsPdf(md, 'test');

    const texts = allTextStrings();
    expect(texts.some((t) => t.includes('console.log'))).toBe(true);
  });

  it('strips inline markdown formatting', async () => {
    await printContentAsPdf('This is **bold** and *italic*', 'test');

    const texts = allTextStrings();
    expect(texts.some((t) => t.includes('bold') && !t.includes('**'))).toBe(true);
  });

  it('strips source citations and action markers', async () => {
    await printContentAsPdf('Answer text [source: 1, 2] [action: follow-up]', 'test');

    const allText = allTextStrings().join(' ');
    expect(allText).not.toContain('[source:');
    expect(allText).not.toContain('[action:');
    expect(allText).toContain('Answer text');
  });

  it('handles horizontal rules', async () => {
    await printContentAsPdf('Above\n\n---\n\nBelow', 'test');
    expect(mockDoc.line).toHaveBeenCalled();
  });

  it('adds new page when content overflows', async () => {
    const longContent = Array.from({ length: 200 }, (_, i) => `Line ${i + 1} of content`).join('\n\n');
    await printContentAsPdf(longContent, 'test');
    expect(mockDoc.addPage).toHaveBeenCalled();
  });

  it('renders checklists', async () => {
    await printContentAsPdf('- [x] Done task\n- [ ] Pending task', 'test');

    const texts = allTextStrings();
    expect(texts.some((t) => t.includes('Done task'))).toBe(true);
    expect(texts.some((t) => t.includes('Pending task'))).toBe(true);
    expect(mockDoc.rect).toHaveBeenCalled();
  });

  it('renders tables', async () => {
    const md = '| Name | Age |\n|------|-----|\n| Jan  | 30  |';
    await printContentAsPdf(md, 'test');

    const texts = allTextStrings();
    expect(texts.some((t) => t.includes('Name'))).toBe(true);
    expect(texts.some((t) => t.includes('Jan'))).toBe(true);
  });

  it('handles Polish characters in title', async () => {
    await printContentAsPdf('Treść dokumentu', 'Ąćę łńóśźż');

    expect(mockDoc.save).toHaveBeenCalledOnce();
    const filename: string = mockDoc.save.mock.calls[0][0];
    expect(filename).toContain('Ąćę');
    expect(filename).toMatch(/\.pdf$/);
  });
});

describe('printContentAsPdf – mermaid blocks', () => {
  it('replaces mermaid blocks with [Diagram] placeholder', async () => {
    const md = '```mermaid\ngraph TD\nA-->B\n```';
    await printContentAsPdf(md, 'test');

    const allText = allTextStrings().join(' ');
    expect(allText).toContain('[Diagram]');
    expect(allText).not.toContain('graph TD');
  });
});
