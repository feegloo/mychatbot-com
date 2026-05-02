import Router from '@koa/router'
import { config } from '../config.js'

export const translateRouter = new Router()

// ---------------------------------------------------------------------------
// Ollama-based translation (offline, no API key required)
// Uses Ollama's OpenAI-compatible chat endpoint with a structured prompt.
// ---------------------------------------------------------------------------
async function ollamaTranslate(texts: string[], targetLang: string, sourceLang?: string): Promise<string[]> {
  const fromNote = sourceLang ? ` from ${sourceLang}` : ''
  const results: string[] = []

  for (const text of texts) {
    const prompt =
      `Translate the following text${fromNote} to ${targetLang}. ` +
      `Return ONLY the translated text, no explanations, no quotes, no extra text.\n\n${text}`

    const res = await fetch(`${config.ollamaBaseUrl}/v1/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: config.ollamaChatModel,
        messages: [{ role: 'user', content: prompt }],
        stream: false,
      }),
    })
    if (!res.ok) throw new Error(`Ollama translate HTTP ${res.status}`)
    const data = (await res.json()) as { choices: Array<{ message: { content: string } }> }
    results.push(data.choices[0]?.message?.content?.trim() ?? text)
  }
  return results
}

async function ollamaDetectLanguage(text: string): Promise<{ language: string; confidence: number }> {
  const prompt =
    `Detect the language of the following text. ` +
    `Reply with ONLY the ISO 639-1 two-letter language code (e.g. "en", "pl", "ar"). ` +
    `No explanations.\n\n${text.slice(0, 500)}`

  const res = await fetch(`${config.ollamaBaseUrl}/v1/chat/completions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: config.ollamaChatModel,
      messages: [{ role: 'user', content: prompt }],
      stream: false,
    }),
  })
  if (!res.ok) throw new Error(`Ollama detect HTTP ${res.status}`)
  const data = (await res.json()) as { choices: Array<{ message: { content: string } }> }
  const lang = data.choices[0]?.message?.content?.trim().toLowerCase().slice(0, 5) ?? 'en'
  return { language: lang, confidence: 0.9 }
}

// ---------------------------------------------------------------------------
// Google Cloud Translation (online path — used when LLM_PROVIDER=openai)
// ---------------------------------------------------------------------------
async function googleTranslate(texts: string[], targetLang: string, sourceLang?: string): Promise<string[]> {
  const { Translate } = await import('@google-cloud/translate/build/src/v2/index.js')
  const client = new Translate()
  const options: { from?: string; to: string; format: 'text' } = { to: targetLang, format: 'text' }
  if (sourceLang) options.from = sourceLang
  const [translations] = await client.translate(texts, options)
  return Array.isArray(translations) ? translations : [translations]
}

async function googleDetectLanguage(text: string): Promise<{ language: string; confidence: number }> {
  const { Translate } = await import('@google-cloud/translate/build/src/v2/index.js')
  const client = new Translate()
  const [detection] = await client.detect(text.slice(0, 500))
  const det = Array.isArray(detection) ? detection[0] : detection
  return { language: det.language, confidence: det.confidence }
}

/**
 * POST /translate
 * Body: { texts: string[], targetLang: string, sourceLang?: string }
 * Returns: { translations: string[] }
 */
translateRouter.post('/translate', async (ctx) => {
  const { texts, targetLang, sourceLang } = ctx.request.body as {
    texts: string[]
    targetLang: string
    sourceLang?: string
  }

  if (!Array.isArray(texts) || !texts.length || !targetLang) {
    ctx.status = 400
    ctx.body = { error: 'texts (string[]) and targetLang are required' }
    return
  }

  if (texts.length > 20) {
    ctx.status = 400
    ctx.body = { error: 'Maximum 20 texts per request' }
    return
  }

  try {
    const translations =
      config.llmProvider === 'ollama'
        ? await ollamaTranslate(texts, targetLang, sourceLang)
        : await googleTranslate(texts, targetLang, sourceLang)

    ctx.body = { translations }
  } catch (err: any) {
    console.error('Translation error:', err.message)
    ctx.status = 502
    ctx.body = { error: 'Translation service unavailable' }
  }
})

/**
 * POST /detect-language
 * Body: { text: string }
 * Returns: { language: string, confidence: number }
 */
translateRouter.post('/detect-language', async (ctx) => {
  const { text } = ctx.request.body as { text: string }

  if (!text) {
    ctx.status = 400
    ctx.body = { error: 'text is required' }
    return
  }

  try {
    const result =
      config.llmProvider === 'ollama'
        ? await ollamaDetectLanguage(text)
        : await googleDetectLanguage(text)

    ctx.body = result
  } catch (err: any) {
    console.error('Language detection error:', err.message)
    ctx.status = 502
    ctx.body = { error: 'Language detection service unavailable' }
  }
})

