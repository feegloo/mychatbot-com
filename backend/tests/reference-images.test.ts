import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import type { UploadedFileRecord } from '../src/types'
import {
  MAX_AUTO_REFERENCE_IMAGES,
  pickAutoReferenceFiles,
  resolveReferenceImagePaths,
} from '../src/utils/reference-images'

function makeFile(
  overrides: Partial<UploadedFileRecord> & Pick<UploadedFileRecord, 'original_name'>,
): UploadedFileRecord {
  return {
    id: overrides.id ?? `id-${overrides.original_name}`,
    conversation_id: overrides.conversation_id ?? 'conv1',
    original_name: overrides.original_name,
    stored_name: overrides.stored_name ?? overrides.original_name,
    mime_type: overrides.mime_type ?? 'application/octet-stream',
    size_bytes: overrides.size_bytes ?? 1,
    storage_key: overrides.storage_key ?? `conv1/${overrides.stored_name ?? overrides.original_name}`,
    metadata_json: overrides.metadata_json,
  }
}

describe('pickAutoReferenceFiles', () => {
  it('keeps only image file extensions supported by gpt-image-1 edits', () => {
    const files = [
      makeFile({ original_name: 'notes.pdf' }),
      makeFile({ original_name: 'photo.PNG' }),
      makeFile({ original_name: 'scan.jpeg' }),
      makeFile({ original_name: 'image.gif' }), // GIF is not accepted by the edit endpoint
      makeFile({ original_name: 'diagram.webp' }),
    ]
    const picked = pickAutoReferenceFiles(files).map((f) => f.original_name)
    expect(picked).toEqual(['photo.PNG', 'scan.jpeg', 'diagram.webp'])
  })

  it('caps the reference list to the most recent uploads', () => {
    const files = Array.from({ length: MAX_AUTO_REFERENCE_IMAGES + 2 }, (_, i) =>
      makeFile({ original_name: `img-${i}.png` }),
    )
    const picked = pickAutoReferenceFiles(files).map((f) => f.original_name)
    // Oldest (img-0, img-1) are dropped; tail is preserved
    expect(picked).toEqual([
      'img-2.png',
      'img-3.png',
      'img-4.png',
      'img-5.png',
    ])
  })
})

describe('resolveReferenceImagePaths', () => {
  let tmpRoot: string

  beforeEach(async () => {
    tmpRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'ref-images-'))
  })

  afterEach(async () => {
    await fs.rm(tmpRoot, { recursive: true, force: true })
  })

  it('returns explicit file names joined to the storage dir, ignoring uploads', async () => {
    const storageDir = path.join(tmpRoot, 'conv1')
    const paths = await resolveReferenceImagePaths({
      explicitFileNames: ['foo.png', 'bar.jpg'],
      files: [makeFile({ original_name: 'baz.png' })],
      storageDir,
      storageRoot: tmpRoot,
    })
    expect(paths).toEqual([path.join(storageDir, 'foo.png'), path.join(storageDir, 'bar.jpg')])
  })

  it('auto-picks uploaded images present on disk when no explicit list given', async () => {
    const namespace = 'conv1'
    const localDir = path.join(tmpRoot, namespace)
    await fs.mkdir(localDir, { recursive: true })
    await fs.writeFile(path.join(localDir, 'IMG_2886.jpeg'), 'bytes')
    // This one is missing on disk on purpose — should be skipped when no GCS
    // hydrate callback is available.
    const missingFile = makeFile({
      original_name: 'IMG_missing.png',
      stored_name: 'IMG_missing.png',
      storage_key: `${namespace}/IMG_missing.png`,
    })
    const presentFile = makeFile({
      original_name: 'IMG_2886.jpeg',
      stored_name: 'IMG_2886.jpeg',
      storage_key: `${namespace}/IMG_2886.jpeg`,
    })

    const paths = await resolveReferenceImagePaths({
      explicitFileNames: undefined,
      files: [missingFile, presentFile],
      storageDir: localDir,
      storageRoot: tmpRoot,
    })

    expect(paths).toEqual([path.join(localDir, 'IMG_2886.jpeg')])
  })

  it('hydrates missing files from GCS before returning them', async () => {
    const namespace = 'conv1'
    const localDir = path.join(tmpRoot, namespace)
    const file = makeFile({
      original_name: 'hero.png',
      stored_name: 'hero.png',
      storage_key: `${namespace}/hero.png`,
    })

    const hydrate = vi.fn(async (_key: string, localPath: string) => {
      await fs.mkdir(path.dirname(localPath), { recursive: true })
      await fs.writeFile(localPath, 'downloaded')
    })

    const paths = await resolveReferenceImagePaths({
      explicitFileNames: undefined,
      files: [file],
      storageDir: localDir,
      storageRoot: tmpRoot,
      hydrateFromGcs: hydrate,
    })

    expect(hydrate).toHaveBeenCalledOnce()
    expect(paths).toEqual([path.join(localDir, 'hero.png')])
  })

  it('reports hydration errors via callback and skips the file', async () => {
    const namespace = 'conv1'
    const file = makeFile({
      original_name: 'broken.png',
      stored_name: 'broken.png',
      storage_key: `${namespace}/broken.png`,
    })
    const onHydrateError = vi.fn()

    const paths = await resolveReferenceImagePaths({
      explicitFileNames: undefined,
      files: [file],
      storageDir: path.join(tmpRoot, namespace),
      storageRoot: tmpRoot,
      hydrateFromGcs: async () => {
        throw new Error('gcs offline')
      },
      onHydrateError,
    })

    expect(paths).toEqual([])
    expect(onHydrateError).toHaveBeenCalledOnce()
    expect(onHydrateError.mock.calls[0][0]).toBe(`${namespace}/broken.png`)
  })
})
