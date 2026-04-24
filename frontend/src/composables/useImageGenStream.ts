import type { ChatMessage } from '../api'
import { announceImage, generateImageStream } from '../api'
import { getStorageUrl } from '../api'
import { getUserId } from '../utils/fingerprint'

export type ImageGenStreamResponse = {
  answer: string
  citations: Array<{
    fileName: string
    chunkId: string
    text: string
    section?: string
    page?: number | null
  }>
  userMessageId?: string
  assistantMessageId?: string
  generatedImage?: {
    fileName: string
    imagePrompt: string
    revisedPrompt: string
    imageTitle: string
  }
}

/**
 * Drives the progressive image-generation flow for a pending assistant
 * message: kicks off the fast announcement call in parallel, consumes
 * the NDJSON stream, and mutates `reactiveMsg` in place so Vue picks up
 * partial frames, the announcement text, and the final answer.
 *
 * Returns the final server response so callers can fire follow-up work
 * (scroll-to-bottom, reload conversation).
 */
export async function runImageGenStream(options: {
  conversationId: string
  question: string
  reactiveMsg: ChatMessage
  timeoutMs?: number
  useUserId?: boolean
}): Promise<ImageGenStreamResponse> {
  const { conversationId, question, reactiveMsg, useUserId = true } = options
  const timeoutMs = options.timeoutMs ?? 120_000

  reactiveMsg.generatingImage = true
  reactiveMsg.imageDetailedPrompt = undefined

  announceImage(conversationId, question)
    .then(({ announcement }) => {
      if (announcement && reactiveMsg.generatingImage) {
        reactiveMsg.imageAnnouncement = announcement
      }
    })
    .catch(() => {})

  const userId = useUserId ? getUserId() || undefined : undefined
  const minMorphMs = 700
  let firstPartialAt: number | null = null

  const settleAfterMinMorph = (resolve: (value: ImageGenStreamResponse) => void, data: ImageGenStreamResponse) => {
    if (firstPartialAt === null) {
      resolve(data)
      return
    }
    const elapsed = Date.now() - firstPartialAt
    const waitMs = Math.max(0, minMorphMs - elapsed)
    if (waitMs === 0) {
      resolve(data)
      return
    }
    setTimeout(() => resolve(data), waitMs)
  }

  return new Promise<ImageGenStreamResponse>((resolve, reject) => {
    const timeoutHandle = setTimeout(() => {
      reject(new Error('Request timed out'))
    }, timeoutMs)

    generateImageStream(conversationId, question, userId, {
      onPromptReady: (data) => {
        if (data.image_prompt) {
          reactiveMsg.imageDetailedPrompt = data.image_prompt
        }
        if (data.image_title && !reactiveMsg.imageAnnouncement) {
          reactiveMsg.imageAnnouncement = `Generating: ${data.image_title}`
        }
      },
      onPartial: ({ b64, index }) => {
        console.log(`🎬 useImageGenStream: Setting partial frame #${index} (b64 length=${b64.length})`)
        if (firstPartialAt === null) firstPartialAt = Date.now()
        reactiveMsg.imagePartialDataUrl = `data:image/png;base64,${b64}`
        reactiveMsg.imagePartialIndex = index
      },
      onComplete: (data) => {
        clearTimeout(timeoutHandle)

        // Some providers/routes emit only a final image and no partials.
        // Show that final image briefly as a synthetic frame so users still
        // see a morph stage before the final markdown answer appears.
        if (firstPartialAt === null && data.generatedImage?.fileName) {
          reactiveMsg.imagePartialDataUrl = getStorageUrl(conversationId, data.generatedImage.fileName)
          reactiveMsg.imagePartialIndex = 0
          firstPartialAt = Date.now()
        }

        settleAfterMinMorph(resolve, data)
      },
      onError: (message) => {
        clearTimeout(timeoutHandle)
        reject(new Error(message))
      },
    }).catch((err) => {
      clearTimeout(timeoutHandle)
      reject(err)
    })
  })
}
