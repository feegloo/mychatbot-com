import { describe, it, expect } from 'vitest';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

marked.use({ breaks: true, gfm: true });

/** Simplified version of renderMarkdown that mirrors the placeholder approach */
function renderMarkdownWithPlaceholders(content: string): string {
  let normalized = content;

  // Protect [action:] with placeholders before marked
  const actionPlaceholders: string[] = [];
  const actionToken = (idx: number) => `\x01ACTION${idx}\x01`;
  normalized = normalized.replace(/\[action:\s*([^\]]+)\]/g, (_, label: string) => {
    const i = actionPlaceholders.length;
    actionPlaceholders.push(label.trim());
    return actionToken(i);
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
  return result;
}

describe('action button rendering with placeholders', () => {
  it('should preserve \\x01 placeholder through marked + DOMPurify', () => {
    const input = '<p>\x01ACTION0\x01</p>';
    const sanitized = DOMPurify.sanitize(input);
    expect(sanitized).toContain('\x01ACTION0\x01');
  });

  it('should convert [action:] to buttons via placeholder approach', () => {
    const input = 'Some text.\n\n[action:Follow up 1] [action:Follow up 2]';
    const result = renderMarkdownWithPlaceholders(input);
    expect(result).toContain('action-btn');
    expect(result).toContain('Follow up 1');
    expect(result).toContain('Follow up 2');
    expect(result).not.toContain('[action:');
  });

  it('should convert multiple [action:] markers', () => {
    const input = 'Text here.\n\n[action:Do something]\n\n[action:What can I do?] [action:What else?]';
    const result = renderMarkdownWithPlaceholders(input);
    expect(result).toContain('action-btn');
    expect(result).not.toContain('[action:');
  });

  it('should handle multiple actions on same line', () => {
    const input = '[action:Do something] [action:Follow up 1] [action:Follow up 2]';
    const result = renderMarkdownWithPlaceholders(input);
    expect(result).toContain('action-btn');
  });

  it('should handle actions in list items', () => {
    const input = 'I can help:\n- option one\n- option two [action:Upload screenshot 📸] [action:Summarize text 🎨]';
    const result = renderMarkdownWithPlaceholders(input);
    expect(result).toContain('action-btn');
    expect(result).toContain('Upload screenshot 📸');
    expect(result).toContain('Summarize text 🎨');
  });

  it('should handle actions with URLs inside', () => {
    const input = 'Check [action:Upload onet.pl screenshot for analysis 📸] [action:Summarize website text 🎨]';
    const result = renderMarkdownWithPlaceholders(input);
    expect(result).toContain('action-btn');
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
      '[action:What can I do while scars heal? 🤔] [action:What signs mean my scar is ready? 🔍]'
    ].join('\n');
    const result = renderMarkdownWithPlaceholders(input);
    expect(result).toContain('action-btn');
    expect(result).toContain('What can I do while scars heal?');
    expect(result).toContain('What signs mean my scar is ready?');
    expect(result).not.toContain('[action:');
  });
});
