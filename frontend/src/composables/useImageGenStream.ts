import type { ChatMessage } from '../api'
import { announceImage, generateImageStream } from '../api'
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
  language?: string
  referenceImageFileNames?: string[]
  onAnnouncement?: () => void
}): Promise<ImageGenStreamResponse> {
  const {
    conversationId,
    question,
    reactiveMsg,
    useUserId = true,
    language,
    referenceImageFileNames,
    onAnnouncement,
  } = options
  const timeoutMs = options.timeoutMs ?? 120_000

  reactiveMsg.generatingImage = true
  reactiveMsg.imageDetailedPrompt = undefined

  // Fires once when the announcement text first appears so callers can
  // auto-scroll to keep the loading indicator visible.
  let announcementNotified = false
  const notifyAnnouncement = () => {
    if (announcementNotified) return
    announcementNotified = true
    onAnnouncement?.()
  }

  announceImage(conversationId, question, language)
    .then(({ announcement }) => {
      if (announcement && reactiveMsg.generatingImage) {
        reactiveMsg.imageAnnouncement = announcement
        notifyAnnouncement()
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
        if (data.image_title) {
          reactiveMsg.imageTitle = data.image_title
        }
        if (data.image_title && !reactiveMsg.imageAnnouncement) {
          reactiveMsg.imageAnnouncement = `Generating: ${data.image_title}`
          notifyAnnouncement()
        }
      },
      onPartial: ({ b64, index }) => {
        console.debug(`🎬 useImageGenStream: Setting partial frame #${index} (b64 length=${b64.length})`)
        if (firstPartialAt === null) firstPartialAt = Date.now()
        // Detect the actual image format from the base64 magic bytes rather
        // than assuming PNG. With output_format="jpeg" the partial frames are
        // JPEG; PNG partials start with "iVBO", JPEG with "/9j/".
        const mime = b64.startsWith('/9j/') ? 'image/jpeg'
          : b64.startsWith('iVBO') ? 'image/png'
          : 'image/jpeg'
        reactiveMsg.imagePartialDataUrl = `data:${mime};base64,${b64}`
        reactiveMsg.imagePartialIndex = index
      },
      onComplete: (data) => {
        if (data.generatedImage?.imageTitle) {
          reactiveMsg.imageTitle = data.generatedImage.imageTitle
        }
        clearTimeout(timeoutHandle)

        settleAfterMinMorph(resolve, data)
      },
      onError: (message, openaiMessage) => {
        clearTimeout(timeoutHandle)
        const err = new Error(message) as Error & { openaiMessage?: string }
        if (openaiMessage) err.openaiMessage = openaiMessage
        reject(err)
      },
    }, language, referenceImageFileNames).catch((err) => {
      clearTimeout(timeoutHandle)
      reject(err)
    })
  })
}
