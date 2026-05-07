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

import { printContentAsPdf, printAssistantMessagesAsPdf, printQuizAsPdf } from '../../src/utils/printPdf';
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
    textWithLink: vi.fn(),
    line: vi.fn(),
    rect: vi.fn(),
    roundedRect: vi.fn(),
    addPage: vi.fn(),
    addImage: vi.fn(),
    save: vi.fn(),
    setPage: vi.fn(),
    getNumberOfPages: vi.fn().mockReturnValue(1),
    getTextWidth: vi.fn().mockReturnValue(20),
    setGState: vi.fn(),
    GState: function GState(this: any, _opts: any) { return this },
    splitTextToSize: vi.fn().mockImplementation((text: string, _width: number) => [text]),
    circle: vi.fn(),
  };
});

function allTextStrings(): string[] {
  return mockDoc.text.mock.calls.map(([t]: [unknown]) =>
    Array.isArray(t) ? t.join(' ') : String(t),
  );
}

// drawWrappedLine calls doc.text once per inline piece (word/space/etc.).
// Join with empty string to reconstruct readable runs for content assertions.
function allJoinedText(): string {
  return allTextStrings().join('');
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

    expect(allJoinedText()).toContain('Main Title');
    expect(allJoinedText()).toContain('Some paragraph');
  });

  it('renders unordered list items with bullet', async () => {
    await printContentAsPdf('- Item one\n- Item two', 'test');

    const texts = allTextStrings();
    expect(texts.some((t) => t === '•')).toBe(true);
    expect(allJoinedText()).toContain('Item one');
    expect(allJoinedText()).toContain('Item two');
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

    const allText = allJoinedText();
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

    expect(allJoinedText()).toContain('Done task');
    expect(allJoinedText()).toContain('Pending task');
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

  it('renders color tags as colored text', async () => {
    await printContentAsPdf('[c:blue]wolność[/c] and [c:purple]Człowiek[/c]', 'test');

    const texts = allTextStrings();
    expect(texts.some((t) => t.includes('wolność'))).toBe(true);
    expect(texts.some((t) => t.includes('Człowiek'))).toBe(true);
    // Blue: [147, 197, 253] and purple: [196, 181, 253] should be set
    const colorCalls = mockDoc.setTextColor.mock.calls;
    expect(colorCalls.some(([r, g, b]: number[]) => r === 147 && g === 197 && b === 253)).toBe(true);
    expect(colorCalls.some(([r, g, b]: number[]) => r === 196 && g === 181 && b === 253)).toBe(true);
  });

  it('strips color tags from text, not from content', async () => {
    await printContentAsPdf('[c:gray]religię[/c:gray] bez Boga', 'test');

    const texts = allTextStrings();
    const allText = texts.join(' ');
    expect(allText).toContain('religię');
    expect(allText).not.toContain('[c:');
    expect(allText).not.toContain('[/c');
  });

  it('falls back to black for unknown color names', async () => {
    await printContentAsPdf('[c:unknown]rendered text[/c]', 'test');

    const texts = allTextStrings();
    // Text is split into word-level pieces, so check individual words
    expect(texts.some((t) => t.includes('rendered') || t.includes('text'))).toBe(true);
    // setTextColor(0, 0, 0) for black (no known color → falls back)
    const colorCalls = mockDoc.setTextColor.mock.calls;
    expect(colorCalls.some(([r, g, b]: number[]) => r === 0 && g === 0 && b === 0)).toBe(true);
  });
});

describe('printContentAsPdf – mermaid blocks', () => {
  it('replaces mermaid blocks with [Diagram] placeholder', async () => {
    const md = '```mermaid\ngraph TD\nA-->B\n```';
    await printContentAsPdf(md, 'test');

    const allText = allTextStrings().join(' ');
    expect(allText).toContain('[Diagram could not be rendered]');
    expect(allText).not.toContain('graph TD');
  });
});

// ── Image caption stripping ───────────────────────────────────────────────

describe('printContentAsPdf – image caption cleanup', () => {
  it('strips <p class="image-caption"> HTML from PDF output', async () => {
    const md = [
      '![Stirner](img.jpg)',
      '',
      '<p class="image-caption">"Stirner i rozpad widm" [1][2][3][4]</p>',
    ].join('\n');

    await printContentAsPdf(md, 'test');

    const allText = allTextStrings().join(' ');
    expect(allText).not.toContain('<p');
    expect(allText).not.toContain('image-caption');
    expect(allText).not.toContain('[1][2][3][4]');
  });

  it('strips <p class="image-caption"> with extra attributes', async () => {
    const md = '<p class="image-caption" style="color:red">Caption text [1]</p>';
    await printContentAsPdf(md, 'test');
    const allText = allTextStrings().join(' ');
    expect(allText).not.toContain('image-caption');
    expect(allText).not.toContain('Caption text');
  });
});

// ── printQuizAsPdf ────────────────────────────────────────────────────────

describe('printQuizAsPdf', () => {
  const sampleQuiz = {
    title: 'History Quiz',
    multiple: false,
    questions: [
      { q: 'Who wrote Hamlet?', options: ['Dickens', 'Shakespeare', 'Tolkien', 'Austen'], correct: [1] },
      { q: 'Capital of France?', options: ['London', 'Berlin', 'Paris', 'Rome'], correct: [2] },
    ],
  };

  it('renders quiz title and questions', async () => {
    await printQuizAsPdf(sampleQuiz, 'quiz-test.pdf');
    const allText = allTextStrings().join(' ');
    expect(allText).toContain('History Quiz');
    expect(allText).toContain('Who wrote Hamlet?');
    expect(allText).toContain('Capital of France?');
  });

  it('renders name/date line when no state provided (blank worksheet)', async () => {
    await printQuizAsPdf(sampleQuiz, 'quiz-test.pdf');
    const allText = allTextStrings().join(' ');
    expect(allText).toContain('Name:');
    expect(allText).toContain('Date:');
  });

  it('does not render name/date line when state is provided', async () => {
    await printQuizAsPdf(sampleQuiz, 'quiz-test.pdf', {
      selections: {},
      submitted: {},
      wrongOptions: {},
    });
    const allText = allTextStrings().join(' ');
    expect(allText).not.toContain('Name:');
  });

  it('calls doc.save with the provided filename', async () => {
    await printQuizAsPdf(sampleQuiz, 'my-quiz.pdf');
    expect(mockDoc.save).toHaveBeenCalledWith('my-quiz.pdf');
  });

  it('renders score summary when all questions submitted', async () => {
    await printQuizAsPdf(sampleQuiz, 'quiz.pdf', {
      selections: { 0: new Set([1]), 1: new Set([2]) },
      submitted: { 0: true, 1: true },
      wrongOptions: { 0: new Set(), 1: new Set() },
    });
    const allText = allTextStrings().join(' ');
    expect(allText).toContain('Score:');
  });

  it('does not render score when not all submitted', async () => {
    await printQuizAsPdf(sampleQuiz, 'quiz.pdf', {
      selections: { 0: new Set([1]) },
      submitted: { 0: true },
      wrongOptions: {},
    });
    const allText = allTextStrings().join(' ');
    expect(allText).not.toContain('Score:');
  });
});

// ── Quiz blocks in conversation PDF ──────────────────────────────────────

describe('printContentAsPdf – quiz blocks inline', () => {
  const quizJson = JSON.stringify({
    title: 'Inline Quiz',
    multiple: true,
    questions: [
      { q: 'What is 2+2?', options: ['3', '4', '5', '6'], correct: [1] },
    ],
  });

  it('renders quiz title when content contains [quiz:{...}]', async () => {
    const md = `Here is a quiz:\n\n[quiz:${quizJson}]`;
    await printContentAsPdf(md, 'test');
    const allText = allTextStrings().join(' ');
    expect(allText).toContain('Inline Quiz');
    expect(allText).toContain('What is 2+2?');
  });

  it('does not print raw [quiz: marker as plain text', async () => {
    const md = `[quiz:${quizJson}]`;
    await printContentAsPdf(md, 'test');
    const allText = allTextStrings().join(' ');
    expect(allText).not.toContain('[quiz:');
    expect(allText).not.toContain('[QUIZ_BLOCK_');
  });
});

// ── printAssistantMessagesAsPdf includes quiz messages ────────────────────

describe('printAssistantMessagesAsPdf – includes quiz messages', () => {
  const quizJson = JSON.stringify({
    title: 'Full Conversation Quiz',
    multiple: false,
    questions: [{ q: 'Question?', options: ['A', 'B', 'C', 'D'], correct: [0] }],
  });

  it('does not skip messages containing [quiz:]', async () => {
    const messages = [
      { content: 'Normal answer' },
      { content: `[quiz:${quizJson}]` },
    ];
    await printAssistantMessagesAsPdf(messages, 'conversation');
    const allText = allTextStrings().join(' ');
    expect(allText).toMatch(/Normal\s+answer/);
    expect(allText).toContain('Full Conversation Quiz');
  });
});

// ── Poem/Quote block wrapping ─────────────────────────────────────────────
// Layout constants (mirror what createLayout computes in tests):
//   pageWidth=210, marginLeft=20, marginRight=20 → contentWidth=170
//   BLOCK_TEXT_PADDING=16 → wrap width=154
//   BLOCK_LINE_H=6, BLOCK_QUOTE_MARK_H=8, BLOCK_PADDING=6

describe('printContentAsPdf – quote block wrapping', () => {
  it('calls splitTextToSize with contentWidth minus BLOCK_TEXT_PADDING (154)', async () => {
    await printContentAsPdf('[quote]\nAny quote text here\n[/quote]', 'test')

    const splitCalls = mockDoc.splitTextToSize.mock.calls as [string, number][]
    expect(splitCalls.some(([, w]) => w === 154)).toBe(true)
  })

  it('sizes the bubble from wrapped line count, not raw line count', async () => {
    // Override splitTextToSize: return 2 wrapped lines for the body text
    mockDoc.splitTextToSize.mockImplementation((text: string, width: number) =>
      width === 154 ? ['first wrapped line', 'second wrapped line'] : [text],
    )

    await printContentAsPdf('[quote]\nA very long quote line that exceeds the column width\n[/quote]', 'test')

    // blockH = BLOCK_QUOTE_MARK_H(8) + 2*BLOCK_LINE_H(6) + BLOCK_QUOTE_MARK_H(8) + 2*BLOCK_PADDING(6) = 40
    const rectCalls = mockDoc.roundedRect.mock.calls as number[][]
    expect(rectCalls.some((args) => args[3] === 40)).toBe(true)
  })

  it('renders all wrapped body lines via doc.text()', async () => {
    mockDoc.splitTextToSize.mockImplementation((text: string, width: number) =>
      width === 154 ? ['first wrapped line', 'second wrapped line'] : [text],
    )

    await printContentAsPdf('[quote]\nA long line that wraps\n[/quote]', 'test')

    const texts = allTextStrings()
    expect(texts).toContain('first wrapped line')
    expect(texts).toContain('second wrapped line')
  })

  it('renders opening and closing quotation marks', async () => {
    await printContentAsPdf('[quote]\nShort quote\n[/quote]', 'test')

    const texts = allTextStrings()
    expect(texts).toContain('\u201C')
    expect(texts).toContain('\u201D')
  })
})

describe('printContentAsPdf – poem block wrapping', () => {
  it('calls splitTextToSize with contentWidth minus BLOCK_TEXT_PADDING (154)', async () => {
    await printContentAsPdf('[poem]\nAny poem text here\n[/poem]', 'test')

    const splitCalls = mockDoc.splitTextToSize.mock.calls as [string, number][]
    expect(splitCalls.some(([, w]) => w === 154)).toBe(true)
  })

  it('sizes the bubble from wrapped line count, not raw line count', async () => {
    // Override splitTextToSize: return 2 wrapped lines for the body text
    mockDoc.splitTextToSize.mockImplementation((text: string, width: number) =>
      width === 154 ? ['first wrapped line', 'second wrapped line'] : [text],
    )

    await printContentAsPdf('[poem]\nA very long poem line that exceeds the column width\n[/poem]', 'test')

    // blockH = BLOCK_QUOTE_MARK_H(8) + 2*BLOCK_LINE_H(6) + BLOCK_QUOTE_MARK_H(8) + 2*BLOCK_PADDING(6) = 40
    const rectCalls = mockDoc.roundedRect.mock.calls as number[][]
    expect(rectCalls.some((args) => args[3] === 40)).toBe(true)
  })

  it('renders all wrapped body lines via doc.text()', async () => {
    mockDoc.splitTextToSize.mockImplementation((text: string, width: number) =>
      width === 154 ? ['first poem line', 'second poem line'] : [text],
    )

    await printContentAsPdf('[poem]\nA long poem line that wraps\n[/poem]', 'test')

    const texts = allTextStrings()
    expect(texts).toContain('first poem line')
    expect(texts).toContain('second poem line')
  })

  it('renders opening and closing quotation marks', async () => {
    await printContentAsPdf('[poem]\nShort poem\n[/poem]', 'test')

    const texts = allTextStrings()
    expect(texts).toContain('\u201C')
    expect(texts).toContain('\u201D')
  })
})
