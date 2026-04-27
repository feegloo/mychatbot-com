#!/usr/bin/env node
// Generates PNG icons for the ChatRAG Chrome extension.
// Uses only Node.js built-ins — no external dependencies needed.
//
// Usage: node scripts/generate-icons.js

'use strict'

const { deflateSync } = require('zlib')
const { writeFileSync, mkdirSync } = require('fs')
const { join } = require('path')

// ── CRC32 ─────────────────────────────────────────────────────────────────────

const CRC_TABLE = (() => {
  const t = new Uint32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    t[n] = c
  }
  return t
})()

function crc32(buf) {
  let crc = 0xffffffff
  for (let i = 0; i < buf.length; i++) {
    crc = CRC_TABLE[(crc ^ buf[i]) & 0xff] ^ (crc >>> 8)
  }
  return (crc ^ 0xffffffff) >>> 0
}

// ── PNG helpers ───────────────────────────────────────────────────────────────

function u32(n) {
  const b = Buffer.alloc(4)
  b.writeUInt32BE(n >>> 0)
  return b
}

function pngChunk(type, data) {
  const t = Buffer.from(type, 'ascii')
  const combined = Buffer.concat([t, data])
  return Buffer.concat([u32(data.length), t, data, u32(crc32(combined))])
}

function buildPng(width, height, pixelsFn) {
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])

  const ihdr = pngChunk(
    'IHDR',
    Buffer.concat([
      u32(width),
      u32(height),
      Buffer.from([8, 6, 0, 0, 0]), // 8-bit RGBA
    ]),
  )

  // Build raw scanlines: 1 filter byte (0 = None) + width * 4 RGBA bytes
  const raw = Buffer.alloc((1 + width * 4) * height)
  for (let y = 0; y < height; y++) {
    raw[y * (1 + width * 4)] = 0 // filter = None
    for (let x = 0; x < width; x++) {
      const [r, g, b, a] = pixelsFn(x, y, width, height)
      const base = y * (1 + width * 4) + 1 + x * 4
      raw[base] = r
      raw[base + 1] = g
      raw[base + 2] = b
      raw[base + 3] = a
    }
  }

  const idat = pngChunk('IDAT', deflateSync(raw, { level: 6 }))
  const iend = pngChunk('IEND', Buffer.alloc(0))

  return Buffer.concat([sig, ihdr, idat, iend])
}

// ── Icon pixel function ───────────────────────────────────────────────────────
// Draws a purple rounded-rectangle with a subtle gradient and white "CR" text.
// The text is approximated using pre-sampled pixel masks so we stay dependency-free.

// Tiny 5×7 pixel font glyphs for "C" and "R"
const GLYPHS = {
  C: [
    [0, 1, 1, 1, 0],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 0],
    [1, 0, 0, 0, 0],
    [1, 0, 0, 0, 0],
    [1, 0, 0, 0, 1],
    [0, 1, 1, 1, 0],
  ],
  R: [
    [1, 1, 1, 1, 0],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 1, 1, 1, 0],
    [1, 0, 1, 0, 0],
    [1, 0, 0, 1, 0],
    [1, 0, 0, 0, 1],
  ],
}

function iconPixelFn(x, y, w, h) {
  const radius = Math.round(w * 0.22)

  // Rounded-rect mask via corner distance
  const cx = Math.min(x, w - 1 - x)
  const cy = Math.min(y, h - 1 - y)
  const inCorner = cx < radius && cy < radius
  if (inCorner) {
    const dx = radius - cx
    const dy = radius - cy
    if (Math.sqrt(dx * dx + dy * dy) > radius) return [0, 0, 0, 0] // transparent
  }

  // Background gradient: #7C3AED → #5B21B6 top to bottom
  const t = y / (h - 1)
  const bgR = Math.round(0x7c + (0x5b - 0x7c) * t)
  const bgG = Math.round(0x3a + (0x21 - 0x3a) * t)
  const bgB = Math.round(0xed + (0xb6 - 0xed) * t)

  // Skip "CR" rendering for very small icons (16px) — not legible
  if (w <= 20) return [bgR, bgG, bgB, 255]

  // Scale text rendering for icon size
  const scale = Math.max(1, Math.round(w / 32))
  const glyphW = 5 * scale
  const glyphH = 7 * scale
  const gap = scale
  const totalTextW = glyphW * 2 + gap
  const startX = Math.round((w - totalTextW) / 2)
  const startY = Math.round((h - glyphH) / 2)

  const lx = x - startX
  const ly = y - startY

  if (lx >= 0 && ly >= 0 && ly < glyphH) {
    // "C" glyph
    if (lx < glyphW) {
      const gx = Math.floor(lx / scale)
      const gy = Math.floor(ly / scale)
      if (gx < 5 && gy < 7 && GLYPHS.C[gy][gx]) return [255, 255, 255, 255]
    }
    // "R" glyph
    const rx = lx - glyphW - gap
    if (rx >= 0 && rx < glyphW) {
      const gx = Math.floor(rx / scale)
      const gy = Math.floor(ly / scale)
      if (gx < 5 && gy < 7 && GLYPHS.R[gy][gx]) return [255, 255, 255, 255]
    }
  }

  return [bgR, bgG, bgB, 255]
}

// ── Generate all sizes ────────────────────────────────────────────────────────

const iconsDir = join(__dirname, '..', 'icons')
mkdirSync(iconsDir, { recursive: true })

const SIZES = [16, 32, 48, 128]

for (const size of SIZES) {
  const png = buildPng(size, size, iconPixelFn)
  const outPath = join(iconsDir, `icon${size}.png`)
  writeFileSync(outPath, png)
  console.log(`✓  icons/icon${size}.png  (${png.length} bytes)`)
}

console.log('\nAll icons generated successfully.')
