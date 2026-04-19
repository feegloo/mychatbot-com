import Router from '@koa/router'
import path from 'node:path'
import fs from 'node:fs/promises'
import { Readable } from 'node:stream'
import { config } from '../config.js'
import { findStoredName, getStorageNamespace } from '../repositories/conversations.js'
import { generateSignedReadUrl } from '../storage/gcs-storage.js'
import { SHORT_ID_RE } from '../constants.js'

export const storageRouter = new Router()

/** Decode a URI component, returning the original string if decoding fails or is a no-op. */
function safeDecodeURI(value: string): string {
  try {
    const decoded = decodeURIComponent(value)
    return decoded
  } catch {
    return value
  }
}

/**
 * Try to find a file in a directory that matches the target name,
 * accounting for NFC/NFD Unicode normalization differences.
 * Returns the actual filename on disk, or null if not found.
 */
async function findFileInDir(dir: string, targetName: string): Promise<string | null> {
  try {
    const entries = await fs.readdir(dir)
    const nfcTarget = targetName.normalize('NFC')
    const nfdTarget = targetName.normalize('NFD')
    for (const entry of entries) {
      if (entry === targetName) return entry
      const nfcEntry = entry.normalize('NFC')
      if (nfcEntry === nfcTarget || nfcEntry === nfdTarget) return entry
    }
  } catch {
    // Directory doesn't exist or isn't readable
  }
  return null
}

/**
 * GET /storage/:conversationId/:fileName
 * Serves uploaded files and extracted images from the storage directory.
 * Only allows image files (png, jpg, jpeg, gif, webp) for security.
 */
storageRouter.get('/storage/:conversationId/:fileName', async (ctx) => {
  const { conversationId } = ctx.params
  // Explicitly decode the fileName param to handle cases where the router
  // or an intermediate proxy didn't fully decode percent-encoded characters.
  const fileName = safeDecodeURI(ctx.params.fileName).normalize('NFC')

  // Validate conversationId is a 12-char base62 string (prevents path traversal)
  if (!SHORT_ID_RE.test(conversationId)) {
    ctx.status = 400
    ctx.body = { error: 'Invalid conversation ID' }
    return
  }

  // Allow image, document, and text file extensions for preview/download
  const ext = path.extname(fileName).toLowerCase()
  const allowedExts = new Set([
    '.png',
    '.jpg',
    '.jpeg',
    '.gif',
    '.webp',
    '.pdf',
    '.txt',
    '.csv',
    '.json',
    '.doc',
    '.docx',
    '.xls',
    '.xlsx',
    '.pptx',
    '.odt',
    '.ods',
    '.odp',
    '.rtf',
    '.md',
  ])
  if (!allowedExts.has(ext)) {
    ctx.status = 403
    ctx.body = { error: 'File type not allowed' }
    return
  }

  // Sanitize fileName to prevent path traversal
  const safeName = path.basename(fileName)
  // Resolve storage namespace (for threads, files live under parent's directory)
  const namespace = await getStorageNamespace(conversationId)
  const dir = path.join(config.storageRoot, namespace)
  let filePath = path.join(dir, safeName)

  // Ensure resolved path is within storage root
  const resolved = path.resolve(filePath)
  if (!resolved.startsWith(path.resolve(config.storageRoot))) {
    ctx.status = 403
    ctx.body = { error: 'Access denied' }
    return
  }

  // Try exact match first, then NFC/NFD scan, then DB lookup by original_name
  let fileBuffer: Buffer | null = null
  let resolvedStoredName: string | null = null

  try {
    await fs.access(filePath)
    fileBuffer = await fs.readFile(filePath)
  } catch {
    const actualName = await findFileInDir(dir, safeName)
    if (actualName) {
      filePath = path.join(dir, actualName)
      fileBuffer = await fs.readFile(filePath)
    } else {
      // File not found by name on disk — look up stored_name from DB
      resolvedStoredName = await findStoredName(namespace, safeName)
      if (resolvedStoredName) {
        filePath = path.join(dir, resolvedStoredName)
        try {
          await fs.access(filePath)
          fileBuffer = await fs.readFile(filePath)
        } catch {
          // Not on disk — try GCS below
        }
      }
    }
  }

  // For large files (>25 MiB) or files not on disk, redirect to GCS signed URL
  // to avoid Cloud Run's 32 MiB response body limit
  const MAX_PROXY_SIZE = 25 * 1024 * 1024
  if (
    config.storageProvider === 'gcs' &&
    config.gcsBucket &&
    (!fileBuffer || fileBuffer.length > MAX_PROXY_SIZE)
  ) {
    const gcsKey = resolvedStoredName
      ? `${namespace}/${resolvedStoredName}`
      : `${namespace}/${safeName}`
    try {
      const signedUrl = await generateSignedReadUrl(gcsKey)
      // For PDF previews, proxy through same-origin endpoint so pdf.js can use range requests
      // without cross-origin/CORS issues from signed GCS URLs.
      if (ext === '.pdf') {
        const range = ctx.get('range')
        const upstream = await fetch(signedUrl, {
          headers: range ? { Range: range } : {},
        })
        if (!upstream.ok && upstream.status !== 206) {
          ctx.status = upstream.status || 502
          ctx.body = { error: 'Failed to read file from storage' }
          return
        }
        if (!upstream.body) {
          ctx.status = 502
          ctx.body = { error: 'Empty storage response' }
          return
        }

        ctx.status = upstream.status
        const passthroughHeaders = [
          'content-type',
          'content-length',
          'content-range',
          'accept-ranges',
          'etag',
          'last-modified',
        ]
        for (const header of passthroughHeaders) {
          const value = upstream.headers.get(header)
          if (value) ctx.set(header, value)
        }
        ctx.set('Content-Disposition', `inline; filename="${encodeURIComponent(fileName)}"`)
        ctx.set('X-Content-Type-Options', 'nosniff')
        ctx.set('Cache-Control', 'public, max-age=86400')
        ctx.body = Readable.fromWeb(upstream.body)
        return
      }

      ctx.redirect(signedUrl)
      return
    } catch {
      // GCS read failed — fall through to serve from disk buffer if available
    }
  }

  if (!fileBuffer) {
    ctx.status = 404
    ctx.body = { error: 'File not found' }
    return
  }

  const mimeTypes: Record<string, string> = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.pdf': 'application/pdf',
    '.txt': 'text/plain; charset=utf-8',
    '.csv': 'text/csv; charset=utf-8',
    '.md': 'text/markdown; charset=utf-8',
    '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.xls': 'application/vnd.ms-excel',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.odt': 'application/vnd.oasis.opendocument.text',
    '.ods': 'application/vnd.oasis.opendocument.spreadsheet',
    '.odp': 'application/vnd.oasis.opendocument.presentation',
    '.rtf': 'application/rtf',
  }

  const inlineExts = new Set([
    '.png',
    '.jpg',
    '.jpeg',
    '.gif',
    '.webp',
    '.pdf',
    '.txt',
    '.csv',
    '.md',
  ])
  ctx.set('Content-Type', mimeTypes[ext] || 'application/octet-stream')
  if (inlineExts.has(ext)) {
    ctx.set('Content-Disposition', `inline; filename="${encodeURIComponent(fileName)}"`)
    ctx.set('X-Content-Type-Options', 'nosniff')
    ctx.set('Accept-Ranges', 'bytes')
  } else {
    ctx.set('Content-Disposition', `attachment; filename="${encodeURIComponent(fileName)}"`)
  }
  ctx.set('Cache-Control', 'public, max-age=86400')
  ctx.body = fileBuffer
})
