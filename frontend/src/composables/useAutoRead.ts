import { ref, watch, type Ref } from 'vue'
import { synthesizeSpeech, synthesizeSpeechWithCaptions } from '../api'
import { getData, setData } from '../utils/localData'
import {
  type MatchedCaption,
  getLanguageColors,
  extractWordRangesFromRange,
  matchCaptionsToWords,
  alignGhosts,
  ensureHighlightEl,
  ensureGhostEl,
  renderCaptionVisuals,
  findTextRangeInContainer,
} from './captionUtils'

const AUTO_READ_KEY = 'autoReadEnabled'
const MAX_CHUNK_LENGTH = 4096
// OpenAI gpt-4o-mini-tts instructions field max length
const MAX_INSTRUCTIONS_LENGTH = 4096

const TTS_TONE_PREAMBLE =
  'You are a helpful AI assistant reading a response aloud. ' +
  'Speak naturally and clearly. Adapt your tone to the emotional context of the conversation — ' +
  'be caring, empathetic, warm, supportive, patient, reassuring, encouraging, ' +
  'attentive, compassionate, gentle, understanding, and thoughtful as the content demands. ' +
  'If the content is cheerful, let warmth come through. If it discusses difficulties, ' +
  'sound genuinely supportive. Mirror the emotional register of the text.'

/**
 * Build a compact chat-history summary for TTS instructions so the voice
 * model can adopt the right emotional tone for the current answer.
 * Budget: ~2500 chars to leave room for the preamble + welcome context.
 */
function buildTtsInstructions(
  messages: { role: string; content: string }[],
  welcomeContent: string,
): string {
  const parts: string[] = [TTS_TONE_PREAMBLE]

  // Include recent Q&A pairs (last 3 exchanges) as conversational context
  const recentPairs: string[] = []
  let budget = 2500
  for (let i = messages.length - 1; i >= 0 && budget > 0; i--) {
    const m = messages[i]
    const label = m.role === 'user' ? 'User asked' : 'Assistant answered'
    const snippet = cleanTextForTTS(m.content).slice(0, 400)
    const line = `${label}: "${snippet}"`
    if (line.length > budget) break
    budget -= line.length
    recentPairs.unshift(line)
  }
  if (recentPairs.length > 0) {
    parts.push('Recent conversation context:\n' + recentPairs.join('\n'))
  }

  if (welcomeContent) {
    const cleaned = cleanTextForTTS(welcomeContent).slice(0, 600)
    parts.push(`Document context: ${cleaned}`)
  }

  return parts.join('\n\n').slice(0, MAX_INSTRUCTIONS_LENGTH)
}

export function cleanTextForTTS(text: string): string {
  return text
    .replace(/\[source:\s*\d+(?:,\s*\d+)*\]/g, '')
    .replace(/(?<!\w)\[(\d+(?:\s*,\s*\d+)*)\](?!\()/g, '')
    .replace(/\[action:\s*[^\]]+\]/g, '')
    .replace(/\[c:\w+\](.*?)\[\/c(?::\w+)?\]/g, '$1')
    .replace(/\[poem\]\s*\n?([\s\S]*?)\[\/poem\]/gi, '$1')
    .replace(/\[quote\]\s*\n?([\s\S]*?)\[\/quote\]/gi, '$1')
    .replace(/\[quiz:[\s\S]*?\]/g, '')
    .replace(/```mermaid\s*\n[\s\S]*?```/g, '')
    .replace(/!\[.*?\]\(.*?\)/g, '')
    .replace(/<[^>]+>/g, '')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\*{1,3}(.*?)\*{1,3}/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/[\p{Emoji_Presentation}\p{Extended_Pictographic}]\uFE0F?/gu, '')
    .replace(/⚠️?/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

export function splitIntoSentences(text: string): string[] {
  const matches = text.match(/[^.!?]*[.!?]+(?:\s|$)|[^.!?]+$/g)
  if (!matches) return text.trim() ? [text.trim()] : []
  return matches.map((s) => s.trim()).filter((s) => s.length > 0)
}

export function extractPoemOrQuoteForAutoRead(text: string): string | null {
  const poemMatch = text.match(/\[poem\]\s*\n?([\s\S]*?)\[\/poem\]/i)
  if (poemMatch?.[1]?.trim()) return poemMatch[1].trim()
  const quoteMatch = text.match(/\[quote\]\s*\n?([\s\S]*?)\[\/quote\]/i)
  return quoteMatch?.[1]?.trim() || null
}

export function buildSentenceChunkSizes(sentenceCount: number): number[] {
  if (sentenceCount <= 0) return []
  const sizes: number[] = []
  let remaining = sentenceCount
  let currentSize = 1

  while (remaining > 0) {
    const nextSize = Math.min(currentSize, remaining)
    sizes.push(nextSize)
    remaining -= nextSize
    currentSize *= 2
  }

  if (sizes.length >= 2) {
    const last = sizes[sizes.length - 1]
    const previous = sizes[sizes.length - 2]
    if (last < previous) {
      sizes[sizes.length - 2] = previous + last
      sizes.pop()
    }
  }

  return sizes
}

function splitTextByMaxLength(text: string, maxLength = MAX_CHUNK_LENGTH): string[] {
  if (text.length <= maxLength) return [text]

  const words = text.split(/\s+/).filter(Boolean)
  if (!words.length) return []

  const chunks: string[] = []
  let current = ''

  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word
    if (candidate.length <= maxLength) {
      current = candidate
      continue
    }

    if (current) chunks.push(current)
    if (word.length <= maxLength) {
      current = word
      continue
    }

    // Extremely long unbroken tokens (e.g., malformed URLs) must be hard-split
    // to satisfy backend TTS max input limits.
    let start = 0
    while (start < word.length) {
      const piece = word.slice(start, start + maxLength)
      chunks.push(piece)
      start += maxLength
    }
    current = ''
  }

  if (current) chunks.push(current)
  return chunks
}

export function buildSynthesisChunks(sentences: string[]): string[] {
  if (!sentences.length) return []

  const chunkSizes = buildSentenceChunkSizes(sentences.length)
  const chunks: string[] = []
  let cursor = 0

  for (const size of chunkSizes) {
    const chunkText = sentences
      .slice(cursor, cursor + size)
      .join(' ')
      .trim()
    cursor += size
    if (!chunkText) continue
    chunks.push(...splitTextByMaxLength(chunkText))
  }

  return chunks
}

export function useAutoRead(
  messages: Ref<{ role: string; content: string }[]>,
  asking: Ref<boolean>,
  welcomeMessage?: Ref<string>,
  containerRef?: Ref<HTMLElement | null>,
  currentLanguage?: Ref<string>,
) {
  const browserLang = navigator.language.split('-')[0]
  const enabled = ref(getData<boolean>(AUTO_READ_KEY) ?? false)

  let currentAudio: HTMLAudioElement | null = null
  let currentBlobUrl: string | null = null
  let aborted = false

  // ── Caption overlay state ──
  let captionHighlightEl: HTMLElement | null = null
  let captionGhostEl: HTMLElement | null = null
  let captionAnimFrame: number | null = null
  let activeCaptionWords: MatchedCaption[] | null = null

  function stopCaptionPlayback(): void {
    if (captionAnimFrame !== null) {
      cancelAnimationFrame(captionAnimFrame)
      captionAnimFrame = null
    }
    activeCaptionWords = null
    if (captionHighlightEl) captionHighlightEl.classList.remove('caption-active')
    if (captionGhostEl) captionGhostEl.classList.remove('caption-active')
  }

  function startCaptionAnimation(audio: HTMLAudioElement): void {
    let lastIdx = -1

    function tick() {
      if (!activeCaptionWords || !currentAudio) return

      const time = audio.currentTime
      let currentIdx = -1

      for (let i = 0; i < activeCaptionWords.length; i++) {
        const { caption } = activeCaptionWords[i]
        if (time >= caption.start && time < caption.end) {
          currentIdx = i
          break
        }
      }

      if (currentIdx !== lastIdx) {
        lastIdx = currentIdx
        if (!captionHighlightEl) captionHighlightEl = ensureHighlightEl(null)
        if (!captionGhostEl) captionGhostEl = ensureGhostEl(null)
        const colors = getLanguageColors(currentLanguage?.value || browserLang)
        renderCaptionVisuals(currentIdx, activeCaptionWords, captionHighlightEl, captionGhostEl, colors)
      }

      captionAnimFrame = requestAnimationFrame(tick)
    }

    captionAnimFrame = requestAnimationFrame(tick)
  }

  function toggle() {
    enabled.value = !enabled.value
    setData(AUTO_READ_KEY, enabled.value)
    if (!enabled.value) {
      stop()
    }
  }

  function stop() {
    aborted = true
    stopCaptionPlayback()
    if (currentAudio) {
      currentAudio.pause()
      currentAudio = null
    }
    if (currentBlobUrl) {
      URL.revokeObjectURL(currentBlobUrl)
      currentBlobUrl = null
    }
  }

  function playAudioBlob(blob: Blob): Promise<void> {
    if (aborted) return Promise.resolve()
    const url = URL.createObjectURL(blob)
    currentBlobUrl = url
    return new Promise<void>((resolve) => {
      const audio = new Audio(url)
      currentAudio = audio
      const cleanup = () => {
        URL.revokeObjectURL(url)
        currentBlobUrl = null
        currentAudio = null
        resolve()
      }
      audio.addEventListener('ended', cleanup)
      audio.addEventListener('error', cleanup)
      audio.play().catch(cleanup)
    })
  }

  function playAudioBlobWithCaptions(blob: Blob): Promise<void> {
    if (aborted) return Promise.resolve()
    const url = URL.createObjectURL(blob)
    currentBlobUrl = url
    return new Promise<void>((resolve) => {
      const audio = new Audio(url)
      currentAudio = audio
      const cleanup = () => {
        stopCaptionPlayback()
        URL.revokeObjectURL(url)
        currentBlobUrl = null
        currentAudio = null
        resolve()
      }
      audio.addEventListener('ended', cleanup)
      audio.addEventListener('error', cleanup)
      audio.play().catch(cleanup)
      if (activeCaptionWords) {
        startCaptionAnimation(audio)
      }
    })
  }

  async function readAloud(text: string) {
    stop()
    aborted = false

    const poemOnlyText = extractPoemOrQuoteForAutoRead(text)
    const cleaned = cleanTextForTTS(poemOnlyText ?? text)
    const sentences = splitIntoSentences(cleaned)
    if (sentences.length === 0) return

    const chunks = buildSynthesisChunks(sentences)
    const instructions = buildTtsInstructions(messages.value, welcomeMessage?.value || '')

    const container = containerRef?.value
    const lang = currentLanguage?.value
    const canUseCaptions = !!(container && lang && lang !== browserLang)

    if (canUseCaptions) {
      // Use captions for single chunk; fall back to basic for multi-chunk
      if (chunks.length === 1) {
        const result = await synthesizeSpeechWithCaptions(
          chunks[0],
          lang,
          browserLang,
          instructions,
        ).catch(() => null)
        if (aborted || !result) return

        if (result.captions && result.captions.length > 0) {
          const textRange = findTextRangeInContainer(container, chunks[0])
          if (textRange) {
            const domWords = extractWordRangesFromRange(textRange)
            const matched = matchCaptionsToWords(result.captions, domWords)
            if (matched.length > 0 && result.translatedText) {
              alignGhosts(matched, result.translatedText)
            }
            activeCaptionWords = matched.length > 0 ? matched : null
          }
        }

        await playAudioBlobWithCaptions(result.audio)
        return
      }

      // Multi-chunk: try captions per chunk sequentially
      for (const chunk of chunks) {
        if (aborted) return
        const result = await synthesizeSpeechWithCaptions(
          chunk,
          lang,
          browserLang,
          instructions,
        ).catch(() => null)
        if (aborted) return
        if (!result) continue

        if (result.captions && result.captions.length > 0) {
          const textRange = findTextRangeInContainer(container, chunk)
          if (textRange) {
            const domWords = extractWordRangesFromRange(textRange)
            const matched = matchCaptionsToWords(result.captions, domWords)
            if (matched.length > 0 && result.translatedText) {
              alignGhosts(matched, result.translatedText)
            }
            activeCaptionWords = matched.length > 0 ? matched : null
          }
        } else {
          activeCaptionWords = null
        }

        await playAudioBlobWithCaptions(result.audio)
        if (aborted) return
      }
      return
    }

    // No container/language: plain synthesis (original behavior)
    const promises = chunks.map((chunk) =>
      synthesizeSpeech(chunk, undefined, instructions).catch(() => null),
    )

    for (const promise of promises) {
      if (aborted) return
      const blob = await promise
      if (aborted) return
      if (blob) await playAudioBlob(blob)
    }
  }

  function stripActionTags(text: string): string {
    return text.replace(/\[action:\s*[^\]]+\]/g, '').trim()
  }

  let prevAsking = asking.value
  watch(asking, (newVal) => {
    if (prevAsking && !newVal && enabled.value) {
      const lastMsg = [...messages.value].reverse().find((m) => m.role === 'assistant')
      if (lastMsg?.content) {
        // Strip [action:...] markers so TTS doesn't read them aloud. The
        // markers live inline in assistant content (same format for welcome
        // messages and normal answers); they are rendered as clickable
        // buttons by the frontend.
        readAloud(stripActionTags(lastMsg.content))
      }
    }
    prevAsking = newVal
  })

  function readWelcomeIfEnabled() {
    if (!enabled.value) return
    const content = welcomeMessage?.value
    if (content) {
      readAloud(stripActionTags(content))
    }
  }

  function cleanup() {
    stop()
  }

  return { enabled, toggle, stop, readAloud, readWelcomeIfEnabled, cleanup }
}
