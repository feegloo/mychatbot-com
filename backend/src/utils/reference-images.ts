/**
 * Helpers for choosing which uploaded files to attach as reference images
 * when the user asks the assistant to generate a new image.
 *
 * The /generate-image route accepts an optional `referenceImageFileNames`
 * list from the caller. When the frontend does not specify any — which is
 * the common case, including suggested action buttons like
 * "Generate an image inspired by: Screenshot 🎨" — we want the generation to
 * stay grounded in the files the user already uploaded instead of letting
 * the model hallucinate a new, unrelated subject. This mirrors the
 * behaviour of the standard chat flow, where uploaded images are always
 * visible to the Vision model via `imageFilePaths`.
 */
import path from 'node:path'
import fs from 'node:fs/promises'
import type { UploadedFileRecord } from '../types.js'

// gpt-image-1's edit endpoint accepts png/jpeg/webp; keep this in sync with
// `_ALLOWED_REFERENCE_MIME` on the Python side.
export const REFERENCE_IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.webp'])

// Matches `MAX_REFERENCE_IMAGES` in python/src/shared/image_gen.py. Capping here
// avoids wasting a round-trip just for the Python side to drop the extras.
export const MAX_AUTO_REFERENCE_IMAGES = 4

/**
 * Pick the most recent uploaded images that are valid as reference inputs
 * for the OpenAI images.edit endpoint. `files` is expected to be ordered
 * oldest-first (matching the ORDER BY created_at ASC used in the
 * conversations repository); we return the tail so the most recently
 * uploaded images win when the user has uploaded more than the cap.
 */
export function pickAutoReferenceFiles(
  files: UploadedFileRecord[],
): UploadedFileRecord[] {
  const images = files.filter((f) =>
    REFERENCE_IMAGE_EXTENSIONS.has(path.extname(f.original_name).toLowerCase()),
  )
  if (images.length <= MAX_AUTO_REFERENCE_IMAGES) return images
  return images.slice(images.length - MAX_AUTO_REFERENCE_IMAGES)
}

/**
 * Resolve the absolute on-disk paths to pass into the Python image generator.
 *
 * - When the caller explicitly supplied file names (already validated by the
 *   route's zod schema), they take precedence and are simply joined with the
 *   conversation's storage dir.
 * - Otherwise we fall back to the recent-uploaded-images heuristic and
 *   hydrate any files that are missing on the local instance from GCS.
 */
export async function resolveReferenceImagePaths(options: {
  explicitFileNames: string[] | undefined
  files: UploadedFileRecord[]
  storageDir: string
  storageRoot: string
  hydrateFromGcs?: (storageKey: string, localPath: string) => Promise<void>
  onHydrateError?: (storageKey: string, err: unknown) => void
}): Promise<string[]> {
  const { explicitFileNames, files, storageDir, storageRoot, hydrateFromGcs, onHydrateError } =
    options

  if (explicitFileNames?.length) {
    return explicitFileNames.map((name) => path.join(storageDir, name))
  }

  const candidates = pickAutoReferenceFiles(files)
  const resolved: string[] = []

  for (const f of candidates) {
    if (!f.storage_key) continue
    const localPath = path.join(storageRoot, f.storage_key)
    try {
      await fs.access(localPath)
    } catch {
      if (!hydrateFromGcs) continue
      try {
        await hydrateFromGcs(f.storage_key, localPath)
      } catch (err) {
        onHydrateError?.(f.storage_key, err)
        continue
      }
    }
    resolved.push(localPath)
  }

  return resolved
}
