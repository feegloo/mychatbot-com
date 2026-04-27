---
name: sync-meta-tags
description: 'Sync the homepage subtitle text from the i18n source (homeLocale.ts, English) to all SEO meta tag locations in index.html. Use when: updating homepage tagline, subtitle, or description copy; keeping og:description, twitter:description, meta description, and JSON-LD in sync with homeLocale.ts; after any edit to the English subtitle fields in frontend/src/i18n/homeLocale.ts (or the legacy <p class="home-subtitle"> in HomeHero.vue/HomePage.vue).'
argument-hint: 'Optional: --dry-run'
---

# Sync Meta Tags from homeLocale.ts

Keeps all 4 SEO description locations in `frontend/index.html` in sync with the
English home-page subtitle copy.

## Source of Truth (in order)

1. `frontend/src/i18n/homeLocale.ts` — `homeMessages.en` fields
   `subtitleP1Html` + `subtitleP1bHtml` + `subtitleP2Html` + `subtitleP3`
   joined with single spaces, HTML stripped.
2. Fallback for older branches: `<p class="home-subtitle">…</p>` inside
   `frontend/src/components/HomeHero.vue` or `frontend/src/pages/HomePage.vue`.

## When to Use

- After editing the English subtitle entries in `homeLocale.ts`
- After editing the legacy `home-subtitle` paragraph in `HomeHero.vue` /
  `HomePage.vue` (fallback path)
- When `meta name="description"`, `og:description`, `twitter:description`, or
  the JSON-LD `description` are stale
- Anytime the user says "sync meta tags", "update SEO copy", or "update
  description in index.html"

## The 4 Locations Updated

1. `<meta name="description" ...>`
2. `<meta property="og:description" ...>`
3. `<meta property="twitter:description" ...>`
4. `"description"` field inside the `<script type="application/ld+json">` block

Note: the Polish (`pl`) entries in `homeMessages` are intentionally **not**
written into `index.html`, because the static SEO copy targets a single
canonical English locale (`<html lang="en">`).

## Procedure

1. Run the sync script (use `--dry-run` to preview without writing):
   ```bash
   node .github/skills/sync-meta-tags/scripts/sync.js
   # or: node .github/skills/sync-meta-tags/scripts/sync.js --dry-run
   ```
2. The script:
   - Reads the English subtitle fields from `homeLocale.ts` (regex-based; does
     not require executing TypeScript).
   - Joins them with spaces, strips HTML tags, collapses whitespace, and
     un-escapes common JS escape sequences (e.g. `\u2019` → `’`).
   - Writes the result into all 4 `index.html` locations.
3. Review the diff in `frontend/index.html` to confirm the update looks correct.

## Script

See [scripts/sync.js](./scripts/sync.js)
