#!/usr/bin/env node
/**
 * Syncs the English home-subtitle text from homeLocale.ts to all 4 SEO
 * description locations in index.html:
 *   1. meta name="description"
 *   2. meta property="og:description"
 *   3. meta property="twitter:description"
 *   4. JSON-LD "description" field
 *
 * Source of truth is the English entry in `homeMessages.en` of
 * `frontend/src/i18n/homeLocale.ts` (subtitleP1Html + subtitleP1bHtml +
 * subtitleP2Html + subtitleP3, joined with single spaces, with HTML stripped).
 *
 * Falls back to scraping `<p class="home-subtitle">` from HomePage.vue or
 * HomeHero.vue for older branches that did not yet extract the copy.
 *
 * Usage: node .github/skills/sync-meta-tags/scripts/sync.js [--dry-run]
 */

import { readFileSync, writeFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
const HOME_LOCALE = resolve(ROOT, "frontend/src/i18n/homeLocale.ts");
const HOME_PAGE = resolve(ROOT, "frontend/src/pages/HomePage.vue");
const HOME_HERO = resolve(ROOT, "frontend/src/components/HomeHero.vue");
const INDEX_HTML = resolve(ROOT, "frontend/index.html");
const DRY_RUN = process.argv.includes("--dry-run");

function htmlToPlain(html) {
  return html
    .replace(/<br\s*\/?>/gi, " ")
    .replace(/<[^>]+>/g, "")
    .replace(/\\u2019/g, "\u2019")
    .replace(/\\u00a0/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function unquote(literal) {
  const quote = literal[0];
  let inner = literal.slice(1, -1);
  if (quote === "'" || quote === '"') {
    inner = inner.replace(/\\(['"\\])/g, "$1");
  }
  return inner;
}

function extractFromLocale() {
  let src;
  try {
    src = readFileSync(HOME_LOCALE, "utf8");
  } catch {
    return null;
  }
  // Isolate the `en: { ... }` block inside `homeMessages = { en: {...}, pl: {...} }`.
  const enBlockMatch = src.match(/en:\s*\{([\s\S]*?)\n\s{2}\},\s*\n\s{2}pl:/);
  if (!enBlockMatch) return null;
  const block = enBlockMatch[1];

  function readField(name) {
    const re = new RegExp(
      String.raw`${name}\s*:\s*((?:'[^']*'|"[^"]*"|\u0060[^\u0060]*\u0060))`,
      "m",
    );
    const m = block.match(re);
    return m ? unquote(m[1]) : null;
  }

  const parts = [
    readField("subtitleP1Html"),
    readField("subtitleP1bHtml"),
    readField("subtitleP2Html"),
    readField("subtitleP3"),
  ].filter(Boolean);
  if (parts.length < 2) return null;
  return htmlToPlain(parts.join(" "));
}

function extractFromVueFallback() {
  for (const path of [HOME_PAGE, HOME_HERO]) {
    let src;
    try {
      src = readFileSync(path, "utf8");
    } catch {
      continue;
    }
    const m = src.match(/<p class="home-subtitle">([\s\S]*?)<\/p>/);
    if (m) {
      const plain = htmlToPlain(m[1]);
      if (plain) return plain;
    }
  }
  return null;
}

let plainText = extractFromLocale();
if (!plainText) plainText = extractFromVueFallback();
if (!plainText) {
  console.error(
    "Could not extract subtitle from homeLocale.ts, HomePage.vue, or HomeHero.vue",
  );
  process.exit(1);
}

console.log("Extracted description:");
console.log(" ", plainText);
console.log();

let html = readFileSync(INDEX_HTML, "utf8");
let changeCount = 0;

function replaceMeta(attrSelector, content) {
  const re = new RegExp(`(${attrSelector}[^>]*content=")[^"]*("\\s*/?>)`, "i");
  const updated = html.replace(re, `$1${content}$2`);
  if (updated === html) {
    console.warn(`  [WARN] Could not find/replace: ${attrSelector}`);
    return;
  }
  html = updated;
  changeCount++;
}

replaceMeta('name="description"', plainText);
replaceMeta('property="og:description"', plainText);
replaceMeta('property="twitter:description"', plainText);

const jsonLdRe = /(\"description\":\s*\")[^\"]*(\",)/;
const updatedJsonLd = html.replace(jsonLdRe, `$1${plainText}$2`);
if (updatedJsonLd !== html) {
  html = updatedJsonLd;
  changeCount++;
} else {
  console.warn('  [WARN] Could not find/replace JSON-LD "description" field');
}

console.log(`Updated ${changeCount}/4 locations.`);

if (DRY_RUN) {
  console.log("[dry-run] No files written.");
} else {
  writeFileSync(INDEX_HTML, html, "utf8");
  console.log(`Written: ${INDEX_HTML}`);
}
