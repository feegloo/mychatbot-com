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
}): Promise<ImageGenStreamResponse> {
  const { conversationId, question, reactiveMsg, useUserId = true } = options
  const timeoutMs = options.timeoutMs ?? 120_000

  reactiveMsg.generatingImage = true

  announceImage(conversationId, question)
    .then(({ announcement }) => {
      if (announcement && reactiveMsg.generatingImage) {
        reactiveMsg.imageAnnouncement = announcement
      }
    })
    .catch(() => {})

  const userId = useUserId ? getUserId() || undefined : undefined

  return new Promise<ImageGenStreamResponse>((resolve, reject) => {
    const timeoutHandle = setTimeout(() => {
      reject(new Error('Request timed out'))
    }, timeoutMs)

    generateImageStream(conversationId, question, userId, {
      onPromptReady: (data) => {
        if (data.image_title && !reactiveMsg.imageAnnouncement) {
          reactiveMsg.imageAnnouncement = `Generating: ${data.image_title}`
        }
      },
      onPartial: ({ b64, index }) => {
        reactiveMsg.imagePartialDataUrl = `data:image/png;base64,${b64}`
        reactiveMsg.imagePartialIndex = index
      },
      onComplete: (data) => {
        clearTimeout(timeoutHandle)
        resolve(data)
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
