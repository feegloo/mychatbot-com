/**
 * Pre-processing utilities for Mermaid diagram source code.
 *
 * Mermaid has strict parsing rules for node labels in square brackets. Certain
 * characters break the parser when they appear in unquoted labels:
 *
 *  - `@`  — parsed as a LINK_ID marker (e.g. email addresses)
 *  - `+`  — parsed as a modifier when it appears at the start of a label
 *           (e.g. phone numbers like `+48 791 421 067`)
 *
 * The AI can generate diagrams with such content (CV data, contact details).
 * `sanitizeMermaidCode` is a best-effort fixup applied before handing code to
 * Mermaid so diagrams render correctly rather than showing a parse error.
 */

/**
 * Wrap unquoted square-bracket node labels that contain problematic characters
 * in double quotes so Mermaid treats them as plain text.
 *
 * Already-quoted labels (`["…"]`) are left untouched.
 */
export function sanitizeMermaidCode(code: string): string {
  return code.replace(
    /(\w+)\[([^\]"[\n]+)\]/g,
    (match, id, label) => {
      const needsQuoting = label.includes('@') || /^\s*\+/.test(label)
      return needsQuoting ? `${id}["${label}"]` : match
    },
  )
}
