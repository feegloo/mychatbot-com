import { describe, it, expect } from 'vitest';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

marked.use({ breaks: true, gfm: true });

/** Simplified version of renderMarkdown that mirrors the placeholder approach */
function renderMarkdownWithPlaceholders(content: string): string {
  let normalized = content;

  // Protect [action:] and [suggest:] with placeholders before marked
  const actionPlaceholders: string[] = [];
  const actionToken = (idx: number) => `\x01ACTION${idx}\x01`;
  normalized = normalized.replace(/\[action:\s*([^\]]+)\]/g, (_, label: string) => {
    const i = actionPlaceholders.length;
    actionPlaceholders.push(label.trim());
    return actionToken(i);
  });
  const suggestPlaceholders: string[] = [];
  const suggestToken = (idx: number) => `\x01SUGGEST${idx}\x01`;
  normalized = normalized.replace(/\[suggest:\s*([^\]]+)\]/g, (_, label: string) => {
    const i = suggestPlaceholders.length;
    suggestPlaceholders.push(label.trim());
    return suggestToken(i);
  });

  const rawHtml = marked.parse(normalized, { async: false }) as string;
  const sanitized = DOMPurify.sanitize(rawHtml);

  // Restore action placeholders
  let result = sanitized.replace(/\x01ACTION(\d+)\x01/g, (_, idxStr: string) => {
    const label = actionPlaceholders[parseInt(idxStr, 10)];
    return `<button class="action-btn" data-action="${label}">${label}</button>`;
  });
  // Wrap action buttons
  result = result.replace(
    /(<button class="action-btn"[^>]*>.*?<\/button>(?:\s*<button class="action-btn"[^>]*>.*?<\/button>)*)/g,
    '<div class="action-btns-row">$1</div>'
  );
  // Restore suggest placeholders
  result = result.replace(/\x01SUGGEST(\d+)\x01/g, (_, idxStr: string) => {
    const label = suggestPlaceholders[parseInt(idxStr, 10)];
    return `<button class="suggest-btn" data-suggest="${label}">${label}</button>`;
  });
  // Wrap suggest buttons
  result = result.replace(
    /(<button class="suggest-btn"[^>]*>.*?<\/button>(?:\s*<button class="suggest-btn"[^>]*>.*?<\/button>)*)/g,
    '<div class="suggest-btns-row">$1</div>'
  );
  return result;
}

describe('suggest rendering with placeholders', () => {
  it('should preserve \\x01 placeholder through marked + DOMPurify', () => {
    const input = '<p>\x01SUGGEST0\x01</p>';
    const sanitized = DOMPurify.sanitize(input);
    expect(sanitized).toContain('\x01SUGGEST0\x01');
  });

  it('should convert [suggest:] to buttons via placeholder approach', () => {
    const input = 'Some text.\n\n[suggest:Follow up 1] [suggest:Follow up 2]';
    const result = renderMarkdownWithPlaceholders(input);
    expect(result).toContain('suggest-btn');
    expect(result).toContain('Follow up 1');
    expect(result).toContain('Follow up 2');
    expect(result).not.toContain('[suggest:');
  });

  it('should convert [action:] and [suggest:] together', () => {
    const input = 'Text here.\n\n[action:Do something]\n\n[suggest:What can I do?] [suggest:What else?]';
    const result = renderMarkdownWithPlaceholders(input);
    expect(result).toContain('action-btn');
    expect(result).toContain('suggest-btn');
    expect(result).not.toContain('[action:');
    expect(result).not.toContain('[suggest:');
  });

  it('should handle action and suggest on same line', () => {
    const input = '[action:Do something] [suggest:Follow up 1] [suggest:Follow up 2]';
    const result = renderMarkdownWithPlaceholders(input);
    expect(result).toContain('action-btn');
    expect(result).toContain('suggest-btn');
  });

  it('should handle suggests in list items', () => {
    const input = 'I can help:\n- option one\n- option two [suggest:Upload screenshot 📸] [suggest:Summarize text 🎨]';
    const result = renderMarkdownWithPlaceholders(input);
    expect(result).toContain('suggest-btn');
    expect(result).toContain('Upload screenshot 📸');
    expect(result).toContain('Summarize text 🎨');
  });

  it('should handle suggests with URLs inside', () => {
    const input = 'Check [suggest:Upload onet.pl screenshot for analysis 📸] [suggest:Summarize website text 🎨]';
    const result = renderMarkdownWithPlaceholders(input);
    expect(result).toContain('suggest-btn');
    expect(result).toContain('Upload onet.pl screenshot for analysis 📸');
  });

  it('should handle realistic full LLM response', () => {
    const input = [
      'Scar treatment should begin **after the natural healing process is complete**. [1][3]',
      '',
      '- **Body scars:** about **9 to 12 months** [1]',
      '- **Facial scars:** about **1 year** [1]',
      '',
      'Starting too early is discouraged. [1][4]',
      '',
      'If you want, I can also summarize what you can do **while scars are still healing**.',
      '',
      '[action:Scar healing guide - summarize next steps]',
      '',
      '[suggest:What can I do while scars heal?] [suggest:What signs mean my scar is ready?]'
    ].join('\n');
    const result = renderMarkdownWithPlaceholders(input);
    expect(result).toContain('action-btn');
    expect(result).toContain('suggest-btn');
    expect(result).toContain('What can I do while scars heal?');
    expect(result).toContain('What signs mean my scar is ready?');
    expect(result).not.toContain('[suggest:');
    expect(result).not.toContain('[action:');
  });
});
