/** Remove storage ID suffix from filename (e.g., "filename_abc123XYZ.ext" -> "filename.ext") */
export function cleanFileName(name: string): string {
  // Strip legacy UUID prefix: "uuid_filename.ext"
  const uuidPrefix = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_/i;
  const cleaned = name.replace(uuidPrefix, "");
  // Strip new short-ID suffix: "filename_<16-char-base62>.ext"
  const shortIdSuffix = /_[0-9A-Za-z]{16}(\.[^.]+)$/;
  return cleaned.replace(shortIdSuffix, "$1");
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
