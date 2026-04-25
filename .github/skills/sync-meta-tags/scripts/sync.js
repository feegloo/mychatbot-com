#!/usr/bin/env node
/**
 * Syncs the home-subtitle text from HomePage.vue to all 4 SEO description
 * locations in index.html:
 *   1. meta name="description"
 *   2. meta property="og:description"
 *   3. meta property="twitter:description"
 *   4. JSON-LD "description" field
 *
 * Usage: node .github/skills/sync-meta-tags/scripts/sync.js [--dry-run]
 */

import { readFileSync, writeFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../../../..')
const HOME_PAGE = resolve(ROOT, 'frontend/src/pages/HomePage.vue')
const INDEX_HTML = resolve(ROOT, 'frontend/index.html')
const DRY_RUN = process.argv.includes('--dry-run')

// --- Extract subtitle from HomePage.vue ---

const vueSource = readFileSync(HOME_PAGE, 'utf8')

// Capture everything inside <p class="home-subtitle">...</p>
const subtitleMatch = vueSource.match(/<p class="home-subtitle">([\s\S]*?)<\/p>/)
if (!subtitleMatch) {
  console.error('Could not find <p class="home-subtitle"> in HomePage.vue')
  process.exit(1)
}

const rawHtml = subtitleMatch[1]

// Convert HTML to a clean plain-text description suitable for meta tags:
//   - <br /> / <br>  → space
//   - <strong>...</strong> → inner text
//   - <span ...>...</span> → inner text
//   - any remaining tags → removed
//   - collapse whitespace
const plainText = rawHtml
  .replace(/<br\s*\/?>/gi, ' ')
  .replace(/<[^>]+>/g, '')
  .replace(/\s+/g, ' ')
  .trim()

console.log('Extracted description:')
console.log(' ', plainText)
console.log()

// --- Update index.html ---

let html = readFileSync(INDEX_HTML, 'utf8')
let changeCount = 0

function replaceMeta(attrSelector, content) {
  const re = new RegExp(`(${attrSelector}[^>]*content=")[^"]*("\\s*/?>)`, 'i')
  const updated = html.replace(re, `$1${content}$2`)
  if (updated === html) {
    console.warn(`  [WARN] Could not find/replace: ${attrSelector}`)
    return
  }
  html = updated
  changeCount++
}

replaceMeta('name="description"', plainText)
replaceMeta('property="og:description"', plainText)
replaceMeta('property="twitter:description"', plainText)

// JSON-LD "description" field (inside application/ld+json script block)
const jsonLdRe = /(\"description\":\s*\")[^\"]*(\",)/
const updatedJsonLd = html.replace(jsonLdRe, `$1${plainText}$2`)
if (updatedJsonLd !== html) {
  html = updatedJsonLd
  changeCount++
} else {
  console.warn('  [WARN] Could not find/replace JSON-LD "description" field')
}

console.log(`Updated ${changeCount}/4 locations.`)

if (DRY_RUN) {
  console.log('[dry-run] No files written.')
} else {
  writeFileSync(INDEX_HTML, html, 'utf8')
  console.log(`Written: ${INDEX_HTML}`)
}
