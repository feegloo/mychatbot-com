import { ref, watch, type Ref } from 'vue'
import { synthesizeSpeech } from '../api'
import { getData, setData } from '../utils/localData'

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
    .replace(/\[c:\w+\](.*?)\[\/c\]/g, '$1')
    .replace(/\[poem\]\s*\n?([\s\S]*?)\[\/poem\]/gi, '$1')
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

export function extractPoemForAutoRead(text: string): string | null {
  const poemMatch = text.match(/\[poem\]\s*\n?([\s\S]*?)\[\/poem\]/i)
  return poemMatch?.[1]?.trim() || null
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
    const chunkText = sentences.slice(cursor, cursor + size).join(' ').trim()
    cursor += size
    if (!chunkText) continue
    chunks.push(...splitTextByMaxLength(chunkText))
  }

  return chunks
}

export function useAutoRead(
  messages: Ref<{ role: string; content: string; suggestedQuestions?: string[] }[]>,
  asking: Ref<boolean>,
  welcomeMessage?: Ref<string>,
) {
  const enabled = ref(getData<boolean>(AUTO_READ_KEY) ?? false)

  let currentAudio: HTMLAudioElement | null = null
  let currentBlobUrl: string | null = null
  let aborted = false

  function toggle() {
    enabled.value = !enabled.value
    setData(AUTO_READ_KEY, enabled.value)
    if (!enabled.value) {
      stop()
    }
  }

  function stop() {
    aborted = true
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

  async function readAloud(text: string) {
    stop()
    aborted = false

    const poemOnlyText = extractPoemForAutoRead(text)
    const cleaned = cleanTextForTTS(poemOnlyText ?? text)
    const sentences = splitIntoSentences(cleaned)
    if (sentences.length === 0) return

    const chunks = buildSynthesisChunks(sentences)
    const instructions = buildTtsInstructions(messages.value, welcomeMessage?.value || '')

    // Fire all synthesis requests in parallel
    const promises = chunks.map((chunk) =>
      synthesizeSpeech(chunk, undefined, instructions).catch(() => null),
    )

    // Play sequentially as each resolves
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
        const questions = lastMsg.suggestedQuestions
        const suffix =
          questions?.length
            ? '\n\n' + questions.map((q) => stripActionTags(q)).join('. ') + '.'
            : ''
        readAloud(lastMsg.content + suffix)
      }
    }
    prevAsking = newVal
  })

  function readWelcomeIfEnabled() {
    if (!enabled.value) return
    const content = welcomeMessage?.value
    if (content) {
      readAloud(content)
    }
  }

  function cleanup() {
    stop()
  }

  return { enabled, toggle, stop, readAloud, readWelcomeIfEnabled, cleanup }
}
