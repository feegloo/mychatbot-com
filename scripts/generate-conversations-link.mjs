#!/usr/bin/env node
/**
 * Generate a shareable ChatRAG URL that pre-loads a set of conversations for
 * any user who clicks the link.
 *
 * Usage:
 *   node scripts/generate-conversations-link.mjs <tokens-file.json> [base-url]
 *
 * Arguments:
 *   tokens-file.json   Path to a JSON file containing an array of
 *                      { "conversationId": "...", "token": "..." } objects.
 *   base-url           Optional. Base URL to use (default: https://chatrag.app).
 *
 * Example:
 *   node scripts/generate-conversations-link.mjs my-tokens.json
 *   node scripts/generate-conversations-link.mjs my-tokens.json https://chatrag.app
 *
 * Input file format (my-tokens.json):
 *   [
 *     { "conversationId": "abc123", "token": "tok_viewer_..." },
 *     { "conversationId": "def456", "token": "tok_viewer_..." }
 *   ]
 *
 * Output:
 *   https://chatrag.app?conversations=<base64url-encoded-tokens>
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const [, , tokensFilePath, baseUrl = 'https://chatrag.app'] = process.argv

if (!tokensFilePath) {
  console.error('Usage: node scripts/generate-conversations-link.mjs <tokens-file.json> [base-url]')
  process.exit(1)
}

const absolutePath = resolve(tokensFilePath)

let entries
try {
  const raw = readFileSync(absolutePath, 'utf-8')
  entries = JSON.parse(raw)
} catch (err) {
  console.error(`Error reading or parsing "${absolutePath}":`, err.message)
  process.exit(1)
}

if (!Array.isArray(entries) || entries.length === 0) {
  console.error('The tokens file must be a non-empty JSON array.')
  process.exit(1)
}

for (const entry of entries) {
  if (
    !entry ||
    typeof entry.conversationId !== 'string' ||
    typeof entry.token !== 'string'
  ) {
    console.error('Each entry must have "conversationId" (string) and "token" (string).')
    console.error('Invalid entry:', JSON.stringify(entry))
    process.exit(1)
  }
}

// Encode: JSON → UTF-8 bytes → base64url (no padding)
const json = JSON.stringify(entries)
const encoded = Buffer.from(json, 'utf-8')
  .toString('base64')
  .replace(/\+/g, '-')
  .replace(/\//g, '_')
  .replace(/=/g, '')

const url = `${baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl}?conversations=${encoded}`

console.log(url)
