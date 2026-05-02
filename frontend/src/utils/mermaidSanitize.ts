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
 * Mermaid also throws "Setting X as parent of X would create a cycle" when a
 * node inside `subgraph X` has the same ID as the subgraph itself.
 *
 * The AI can generate diagrams with such content (CV data, contact details,
 * company names reused as both subgraph and node ID).
 * `sanitizeMermaidCode` is a best-effort fixup applied before handing code to
 * Mermaid so diagrams render correctly rather than showing a parse error.
 */

/**
 * Wrap unquoted square-bracket node labels that contain problematic characters
 * in double quotes so Mermaid treats them as plain text.
 *
 * Already-quoted labels (`["…"]`) are left untouched.
 */
function fixUnquotedLabels(code: string): string {
  return code.replace(
    /(\w+)\[([^\]"[\n]+)\]/g,
    (match, id, label) => {
      const needsQuoting = label.includes('@') || /^\s*\+/.test(label)
      return needsQuoting ? `${id}["${label}"]` : match
    },
  )
}

/**
 * Fix "Setting X as parent of X would create a cycle" Mermaid error.
 *
 * Mermaid throws this when a node inside a `subgraph X` block shares the same
 * ID as the subgraph itself. We detect these conflicts and rename the node ID
 * (by appending "Node") throughout the diagram, leaving the subgraph
 * declaration and node label text untouched.
 */
export function fixSubgraphNodeConflicts(code: string): string {
  const lines = code.split('\n')

  // Pass 1: find node IDs that collide with their enclosing subgraph name.
  const subgraphStack: string[] = []
  const conflictingIds = new Set<string>()

  for (const line of lines) {
    const sgMatch = line.match(/^\s*subgraph\s+(\w+)/)
    if (sgMatch) {
      subgraphStack.push(sgMatch[1])
      continue
    }
    if (/^\s*end\b/.test(line) && subgraphStack.length) {
      subgraphStack.pop()
      continue
    }
    if (subgraphStack.length) {
      const currentSg = subgraphStack[subgraphStack.length - 1]
      // Node definition: (optional whitespace) + currentSg + [, (, or {
      if (new RegExp(`^\\s*${currentSg}[\\[({]`).test(line)) {
        conflictingIds.add(currentSg)
      }
    }
  }

  if (!conflictingIds.size) return code

  // Pass 2: rename each conflicting ID everywhere except:
  //   - subgraph declaration lines (`subgraph X`)
  //   - text inside double-quoted label strings (temporarily replaced by placeholders)
  return lines
    .map(line => {
      if (/^\s*subgraph\s+/.test(line)) return line

      // Temporarily replace quoted label content to avoid renaming text inside labels.
      const placeholders: string[] = []
      let out = line.replace(/"[^"]*"/g, match => {
        placeholders.push(match)
        return `"\x00PH${placeholders.length - 1}\x00"`
      })

      for (const id of conflictingIds) {
        const escaped = id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
        out = out.replace(new RegExp(`\\b${escaped}\\b`, 'g'), `${id}Node`)
      }

      // Restore quoted content
      return out.replace(/"\x00PH(\d+)\x00"/g, (_, i) => placeholders[parseInt(i, 10)])
    })
    .join('\n')
}

export function sanitizeMermaidCode(code: string): string {
  return fixSubgraphNodeConflicts(fixUnquotedLabels(code))
}
