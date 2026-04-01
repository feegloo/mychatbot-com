/** Remove UUID prefix from filename (e.g., "uuid_filename.ext" -> "filename.ext") */
export function cleanFileName(name: string): string {
  const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_/i;
  return name.replace(uuidPattern, "");
}

/** Convert URLs, bare domains and email addresses to clickable HTML links */
export function linkify(text: string): string {
  const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const tlds = '(?:com|org|net|io|dev|pl|eu|co|info|me|app|xyz|tech|ai)';
  const emailRe = `[a-z0-9._%+\\-]+@(?:[a-z0-9\\-]+\\.)+${tlds}`;
  const urlRe = `https?:\\/\\/[^\\s<]+|(?:[a-z0-9](?:[a-z0-9\\-]*[a-z0-9])?\\.)+${tlds}\\b[^\\s<]*`;
  const combined = new RegExp(`(${emailRe}|${urlRe})`, 'gi');
  return escaped.replace(combined, (match) => {
    if (match.includes('@')) {
      return `<a href="mailto:${match}" style="color: #60a5fa;">${match}</a>`;
    }
    const href = match.match(/^https?:\/\//i) ? match : `https://${match}`;
    return `<a href="${href}" target="_blank" rel="noopener noreferrer" style="color: #60a5fa;">${match}</a>`;
  });
}
