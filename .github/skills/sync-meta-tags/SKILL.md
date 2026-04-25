---
name: sync-meta-tags
description: 'Sync the homepage subtitle text from HomePage.vue to all SEO meta tag locations in index.html. Use when: updating homepage tagline, subtitle, or description copy; keeping og:description, twitter:description, meta description, and JSON-LD in sync with HomePage.vue; after any edit to the home-subtitle paragraph in HomePage.vue.'
argument-hint: 'Optional: path overrides, e.g. "dry-run"'
---

# Sync Meta Tags from HomePage.vue

Keeps all 4 SEO description locations in `frontend/index.html` in sync with the `<p class="home-subtitle">` content in `frontend/src/pages/HomePage.vue`.

## When to Use

- After editing the tagline/subtitle in `HomePage.vue`
- When `meta name="description"`, `og:description`, `twitter:description`, or the JSON-LD `description` are stale
- Anytime the user says "sync meta tags", "update SEO copy", or "update description in index.html"

## The 4 Locations Updated

1. `<meta name="description" ...>`
2. `<meta property="og:description" ...>`
3. `<meta property="twitter:description" ...>`
4. `"description"` field inside the `<script type="application/ld+json">` block

## Procedure

1. Run the sync script:
   ```bash
   node .github/skills/sync-meta-tags/scripts/sync.js
   ```
2. The script reads the subtitle from `HomePage.vue`, strips HTML tags to produce plain text, and writes it to all 4 locations in `index.html`.
3. Review the diff to confirm the update looks correct.

## Script

See [scripts/sync.js](./scripts/sync.js)
