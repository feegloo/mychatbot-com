<template>
  <div v-if="detectedLang && availableLangs.length > 1" ref="wrapRef" class="lang-toggle-wrap">
    <button
      class="lang-toggle-btn"
      :title="translating ? 'Translating…' : buttonTitle"
      @click="onButtonClick"
      @pointerup="(e) => (e.currentTarget as HTMLElement).blur()"
    >
      <span class="lang-flag" :class="{ translating }">{{ currentFlag }}</span>
      <svg
        v-if="translating"
        class="lang-spinner"
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.5"
      >
        <path
          d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"
        />
      </svg>
    </button>
    <div v-if="showDropdown" class="lang-dropdown">
      <button
        v-for="lang in dropdownLangs"
        :key="lang"
        class="lang-dropdown-item"
        @click="translateTo(lang)"
      >
        <span class="lang-flag">{{ flagFor(lang) }}</span>
        <span>{{ langName(lang) }}</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import ISO6391 from 'iso-639-1'
import { translateTexts, detectLanguage } from '../api'
import {
  setStoredTranslation,
  getBulkStoredTranslations,
} from '../utils/translationStorage'
import {
  getStoredConversationLanguage,
  storeConversationLanguage,
} from '../utils/conversationLanguage'

// Marker handling for translation:
// - [source:N] markers are fully opaque (numeric id, must not change)
// - [action:Label] markers are also opaque during translation, but their Label
//   text is translated separately and re-inserted so suggested-action buttons
//   appear in the target language.
// - [poem] / [/poem] and [quote] / [/quote] tags are opaque so the literal
//   words "poem"/"quote" aren't translated (e.g. to "wiersz"/"cytat" in Polish),
//   while the verse/quote content between the tags is still translated naturally
//   as part of the surrounding text.
// - ![alt](url) markdown images are opaque: the URL must never be translated
//   (e.g. Pollinations URLs embed the prompt in the path, and translating it
//   produces an unreachable src and a broken-image icon after the v-html swap).
// - [mindmap]...[/mindmap] blocks are fully opaque: the embedded Mermaid
//   diagram syntax (keywords like `mindmap`, `root`, shape markers) must never
//   reach the translation service or it garbles them into the target language
//   (e.g. "mindmap" → "mapa myśli", "`mermaid" → "syrena") breaking rendering.
const MARKER_RE = /\[(source|action):([^\]]*)\]/gi
const POEM_TAG_RE = /\[\/?(?:poem|quote)\]/gi
const MINDMAP_BLOCK_RE = /\[mindmap\][\s\S]*?\[\/mindmap\]/gi
// Language tag: [language]xx[/language] emitted by the model to indicate source document language.
// Protected from translation to ensure the tag survives as-is in translated messages.
const LANGUAGE_TAG_RE = /\[language\][a-z]{2,3}\[\/language\]/gi
// Markdown image: `![alt](url "optional title")`. Uses negated character
// classes so the match stops at the first closing `]` / `)` rather than
// spanning over adjacent links on the same line.
const IMAGE_MD_RE = /!\[[^\]]*\]\([^)\s]+(?:\s+"[^"]*")?\)/g

/**
 * Extract all [quiz:{...}] blocks from a string using brace-counting so that
 * nested JSON brackets don't confuse a simple regex. Returns the text with
 * each quiz block replaced by an opaque placeholder, plus the list of
 * (placeholder → original) pairs needed to restore them after translation.
 */
function extractQuizBlocks(
  text: string,
  textIndex: number,
  counterRef: { value: number },
): { result: string; found: Array<{ placeholder: string; original: string }> } {
  const found: Array<{ placeholder: string; original: string }> = []
  const quizMarker = '[quiz:'
  let result = text
  let searchFrom = 0
  while (searchFrom < result.length) {
    const start = result.indexOf(quizMarker, searchFrom)
    if (start === -1) break
    const jsonStart = start + quizMarker.length
    let depth = 0
    let endIndex = -1
    for (let i = jsonStart; i < result.length; i++) {
      if (result[i] === '{') depth++
      else if (result[i] === '}') {
        depth--
        if (depth === 0) {
          let j = i + 1
          while (j < result.length && /\s/.test(result[j])) j++
          if (j < result.length && result[j] === ']') {
            endIndex = j
          }
          break
        }
      }
    }
    if (endIndex === -1) {
      searchFrom = start + quizMarker.length
      continue
    }
    const original = result.slice(start, endIndex + 1)
    const placeholder = makePlaceholder(textIndex, counterRef.value++)
    found.push({ placeholder, original })
    result = result.slice(0, start) + placeholder + result.slice(endIndex + 1)
    searchFrom = start + placeholder.length
  }
  return { result, found }
}

// Placeholder format chosen to survive round-trips through Google Translate,
// including across-script boundaries (notably Arabic ↔ Latin) where the
// previous `__MRK0_0__` form had its leading underscores silently stripped
// by the translator, leaking raw `MRK0_0__` tokens into the rendered
// message and breaking action-button restoration. Using only letters and
// digits with letter delimiters avoids that class of mangling.
function makePlaceholder(textIndex: number, counter: number): string {
  return `XMRK${textIndex}X${counter}XEND`
}

// Tolerant matcher used as a fallback when an exact-string replace fails.
// The translator can strip or alter the boundary letters (`X`/`END`) when
// crossing scripts (Arabic → Latin observed in production). Match the
// invariant numeric core `MRK<i>X<c>` and consume any surviving boundary
// letters/whitespace around it so the placeholder is fully replaced.
function placeholderRegex(placeholder: string): RegExp {
  // Placeholder shape: `XMRK<i>X<c>XEND`. Extract the numeric core.
  const core = placeholder.replace(/^XMRK/, '').replace(/XEND$/, '')
  return new RegExp(`\\s*X?MRK${core}X?(?:END)?\\s*`, 'i')
}

type MarkerInfo = {
  placeholder: string
  kind: 'source' | 'action' | 'image' | 'poem' | 'quiz' | 'mindmap' | 'langtag'
  original: string
  label?: string // only for action markers; gets replaced with translated label
  // |ref:filename suffix — opaque, must survive translation verbatim
  refSuffix?: string
}

function extractMarkers(texts: string[]): {
  cleaned: string[]
  markers: Map<number, MarkerInfo[]>
} {
  const markers = new Map<number, MarkerInfo[]>()
  const cleaned = texts.map((text, i) => {
    const found: MarkerInfo[] = []
    const counterRef = { value: 0 }
    // Extract quiz blocks first — they contain JSON with nested brackets that
    // would confuse all downstream regexes and break the rendered quiz widget
    // if sent to the translation service.
    const { result: afterQuiz, found: quizFound } = extractQuizBlocks(text, i, counterRef)
    for (const q of quizFound) {
      found.push({ placeholder: q.placeholder, kind: 'quiz', original: q.original })
    }
    // Extract [mindmap]...[/mindmap] blocks entirely — the Mermaid diagram
    // syntax inside must never be sent to the translation service. Keywords
    // like `mindmap`, `root`, and shape markers would be translated into the
    // target language (e.g. Polish: "mapa myśli", "korzeń"), breaking Mermaid.
    const afterMindmap = afterQuiz.replace(MINDMAP_BLOCK_RE, (match) => {
      const placeholder = makePlaceholder(i, counterRef.value++)
      found.push({ placeholder, kind: 'mindmap', original: match })
      return placeholder
    })
    // Extract [language]xx[/language] tags — these are structural metadata
    // emitted by the model to indicate source document language; they must
    // not be sent to the translation service as the tag itself is not content.
    const afterLangTag = afterMindmap.replace(LANGUAGE_TAG_RE, (match) => {
      const placeholder = makePlaceholder(i, counterRef.value++)
      found.push({ placeholder, kind: 'langtag', original: match })
      return placeholder
    })
    // Extract markdown images so their `[alt]` brackets don't collide
    // with the [source:…]/[action:…] marker regex on the following pass.
    let result = afterLangTag.replace(IMAGE_MD_RE, (match) => {
      const placeholder = makePlaceholder(i, counterRef.value++)
      found.push({ placeholder, kind: 'image', original: match })
      return placeholder
    })
    result = result.replace(POEM_TAG_RE, (match) => {
      const placeholder = makePlaceholder(i, counterRef.value++)
      found.push({ placeholder, kind: 'poem', original: match })
      return placeholder
    })
    result = result.replace(MARKER_RE, (match, kind: string, inner: string) => {
      const placeholder = makePlaceholder(i, counterRef.value++)
      const info: MarkerInfo = {
        placeholder,
        kind: kind.toLowerCase() === 'action' ? 'action' : 'source',
        original: match,
      }
      if (info.kind === 'action') {
        const trimmed = inner.trim()
        const refIdx = trimmed.indexOf('|ref:')
        if (refIdx !== -1) {
          // Split translatable display label from the opaque |ref:filename suffix.
          // Only the display part is sent to the translation service; the filename
          // must reach the frontend intact so image-to-image generation works.
          info.label = trimmed.slice(0, refIdx).trim()
          info.refSuffix = trimmed.slice(refIdx)
        } else {
          info.label = trimmed
        }
      }
      found.push(info)
      return placeholder
    })
    if (found.length) markers.set(i, found)
    return result
  })
  return { cleaned, markers }
}

function restoreMarkers(translations: string[], markers: Map<number, MarkerInfo[]>): string[] {
  return translations.map((text, i) => {
    const m = markers.get(i)
    if (!m) return text
    let result = text
    for (const info of m) {
      const replacement =
        info.kind === 'action' && info.label !== undefined
          ? `[action:${info.label}${info.refSuffix ?? ''}]`
          : info.original
      // Exact match first (cheap, common case). Fall back to a tolerant
      // regex when the translator has nudged whitespace or casing around
      // the placeholder — this is what protects action buttons when
      // translating from RTL scripts (e.g. Arabic) into Latin targets.
      if (result.includes(info.placeholder)) {
        result = result.replace(info.placeholder, replacement)
      } else {
        const re = placeholderRegex(info.placeholder)
        if (re.test(result)) {
          result = result.replace(re, replacement)
        }
      }
    }
    return result
  })
}

async function translateBatch(
  texts: string[],
  targetLang: string,
  sourceLang?: string,
): Promise<string[]> {
  // Google Translate route caps each request at 20 items; parallelise chunks
  // so the logical call remains one awaitable batch from the caller's view.
  const out: string[] = new Array(texts.length)
  const chunkJobs: Promise<void>[] = []
  for (let start = 0; start < texts.length; start += 20) {
    const chunk = texts.slice(start, start + 20)
    const offset = start
    chunkJobs.push(
      translateTexts(chunk, targetLang, sourceLang).then((r) => {
        r.translations.forEach((t, k) => {
          out[offset + k] = t
        })
      }),
    )
  }
  await Promise.all(chunkJobs)
  return out
}

async function translateWithMarkers(texts: string[], targetLang: string, sourceLang?: string) {
  const { cleaned, markers } = extractMarkers(texts)
  // Preserve leading/trailing whitespace per text — translation services
  // commonly strip these, which causes visible layout jumps between the
  // original and translated rendering (markdown paragraph/block heights
  // depend on trailing newlines).
  const leading: string[] = []
  const trailing: string[] = []
  const stripped = cleaned.map((t) => {
    const l = t.match(/^\s*/)?.[0] ?? ''
    const r = t.match(/\s*$/)?.[0] ?? ''
    leading.push(l)
    trailing.push(r)
    return t.slice(l.length, t.length - r.length)
  })

  // Flatten text + per-message action labels into a single positional batch.
  // For each message we push its stripped text followed by its action labels
  // contiguously, which is the positional mapping the spec calls for (text
  // at N, its actions at N+1, N+2, …).
  type Slot =
    | { kind: 'text'; textIndex: number }
    | { kind: 'action'; markerRef: MarkerInfo }
  const slots: Slot[] = []
  const batch: string[] = []
  stripped.forEach((s, i) => {
    slots.push({ kind: 'text', textIndex: i })
    batch.push(s)
    const msgMarkers = markers.get(i)
    if (!msgMarkers) return
    for (const mk of msgMarkers) {
      if (mk.kind !== 'action' || !mk.label) continue
      slots.push({ kind: 'action', markerRef: mk })
      batch.push(mk.label)
    }
  })

  const translated = await translateBatch(batch, targetLang, sourceLang)

  // Reassemble: action translations mutate the shared MarkerInfo label so
  // restoreMarkers re-inserts the translated [action:Label] fragment.
  const textTranslations: string[] = new Array(stripped.length)
  slots.forEach((slot, i) => {
    const t = translated[i]
    if (t === undefined) return
    if (slot.kind === 'text') textTranslations[slot.textIndex] = t
    else slot.markerRef.label = t
  })

  const withWhitespace = textTranslations.map((t, i) => leading[i] + t + trailing[i])
  return { translations: restoreMarkers(withWhitespace, markers) }
}

const props = defineProps<{
  messages: Array<{ id?: string; role: string; content: string }>
  title?: string
  conversationId?: string
}>()

const emit = defineEmits<{
  translated: [translations: Map<number, string>]
  'title-translated': [translation: string]
  restored: [newTranslations: Map<number, string>]
  'lang-changed': [language: string]
  'translating-start': []
  'translating-end': []
}>()

const detectedLang = ref('')
// Source document language — extracted from [language]xx[/language] tag in the welcome
// message. For new conversations where the welcome is generated in the user's language,
// this holds the actual language of the source document (e.g. 'en' for an English PDF
// uploaded by a Polish-speaking user). For backward-compatible conversations (no tag),
// it remains empty and detectedLang covers both roles.
const sourceLang = ref('')
const browserLang = ref(navigator.language.split('-')[0])
const currentLang = ref('') // language messages are currently displayed in
// Target language during an in-flight translation. Used so the flag flips
// immediately on click while the translated text fades in asynchronously
// once the API promise resolves.
const pendingLang = ref('')
const translating = ref(false)
const translationCache = ref<Map<string, string>>(new Map())
// In-flight translation promises keyed by target language. We keep them across
// "cancel" clicks (user toggled back to the original while a request is still
// loading) so a subsequent click on the same target awaits the same request
// instead of firing a duplicate. Entries are removed on settle (success OR
// error) so a fresh promise is created on retry.
type PendingTranslation = {
  translations: Map<number, string>
  title?: string
}
const inflightTranslations = new Map<string, Promise<PendingTranslation>>()
const detectionAttempted = ref(false)
const translatedUpToIndex = ref(-1)
const showDropdown = ref(false)
const wrapRef = ref<HTMLElement | null>(null)

function getStoredLanguage(): Promise<string | null> {
  return getStoredConversationLanguage(props.conversationId)
}

async function storeLanguage(lang: string) {
  await storeConversationLanguage(props.conversationId, lang, detectedLang.value)
}

const LANG_FLAGS: Record<string, string> = {
  en: '🇬🇧',
  pl: '🇵🇱',
  de: '🇩🇪',
  fr: '🇫🇷',
  es: '🇪🇸',
  it: '🇮🇹',
  pt: '🇵🇹',
  nl: '🇳🇱',
  ru: '🇷🇺',
  uk: '🇺🇦',
  cs: '🇨🇿',
  sk: '🇸🇰',
  ja: '🇯🇵',
  ko: '🇰🇷',
  zh: '🇨🇳',
  ar: '🇸🇦',
  hi: '🇮🇳',
  tr: '🇹🇷',
  sv: '🇸🇪',
  da: '🇩🇰',
  fi: '🇫🇮',
  no: '🇳🇴',
  hu: '🇭🇺',
  ro: '🇷🇴',
  bg: '🇧🇬',
  hr: '🇭🇷',
  el: '🇬🇷',
  he: '🇮🇱',
  th: '🇹🇭',
  vi: '🇻🇳',
  id: '🇮🇩',
  ms: '🇲🇾',
}

function langName(code: string) {
  // Native/endonym name (e.g. "Polski", "Italiano") so the menu entry matches
  // the flag and is recognisable to speakers of that language.
  return ISO6391.getNativeName(code) || code
}

function flagFor(code: string) {
  return LANG_FLAGS[code] || '🌐'
}

// Available target languages: unique set of {detected, sourceLang, browser, 'en'}
// - detectedLang: language content was generated in (= user lang for new convos, source for old)
// - sourceLang: actual source document language (from [language] tag, if present)
// - browserLang: user's browser language
// - 'en': always available
const availableLangs = computed(() => {
  const set = new Set<string>()
  if (detectedLang.value) set.add(detectedLang.value)
  if (sourceLang.value) set.add(sourceLang.value)
  if (browserLang.value) set.add(browserLang.value)
  set.add('en')
  return [...set]
})

const isToggleMode = computed(() => availableLangs.value.length === 2)

// Languages to show in dropdown (everything except current)
const dropdownLangs = computed(() => availableLangs.value.filter((l) => l !== currentLang.value))

const isTranslated = computed(
  () => currentLang.value !== '' && currentLang.value !== detectedLang.value,
)

const currentFlag = computed(() =>
  flagFor(pendingLang.value || currentLang.value || detectedLang.value),
)

const buttonTitle = computed(() => {
  if (isTranslated.value) {
    return `Showing ${langName(currentLang.value)} — click for ${isToggleMode.value ? 'original' : 'options'}`
  }
  return `Showing original (${langName(detectedLang.value)}) — click to translate`
})

// Close dropdown on outside click
function onClickOutside(e: MouseEvent) {
  if (wrapRef.value && !wrapRef.value.contains(e.target as Node)) {
    showDropdown.value = false
  }
}
onMounted(() => document.addEventListener('click', onClickOutside))
onBeforeUnmount(() => document.removeEventListener('click', onClickOutside))

// Detect language from first assistant message (retries until successful)
watch(
  () => props.messages,
  async (msgs) => {
    if (detectedLang.value || detectionAttempted.value) return
    const firstAssistant = msgs.find((m) => m.role === 'assistant' && m.content.length > 20)
    if (!firstAssistant) return
    detectionAttempted.value = true

    // Fast path: if a stored language exists and translations are cached, apply
    // them immediately — before waiting for the language detection API call.
    // This ensures the page renders in the user's chosen language on refresh.
    const storedLang = await getStoredLanguage()
    if (storedLang) {
      const messageIds = msgs.filter((m) => m.id).map((m) => m.id!)
      const cachedByMessageId = await getBulkStoredTranslations(storedLang, messageIds)
      if (cachedByMessageId.size > 0) {
        const translations = new Map<number, string>()
        msgs.forEach((msg, i) => {
          if (msg.id) {
            const t = cachedByMessageId.get(msg.id)
            if (t) {
              translations.set(i, t)
              translationCache.value.set(`${msg.content}→${storedLang}`, t)
            }
          }
        })
        if (translations.size > 0) {
          currentLang.value = storedLang
          translatedUpToIndex.value = msgs.length - 1
          // Defer until the current render cycle is complete before mutating
          // message content — same pattern as translateTo() below. Without this
          // nextTick the emit fires mid-render, causing setupTooltips() in
          // MessageContent.vue to run while Vue is still patching the DOM,
          // which produces "Cannot destructure property 'value' of 'undefined'"
          // errors in floating-vue's v-tooltip directive hook.
          await nextTick()
          emit('translated', translations)
        }
      }
    }

    // Check for [language]xx[/language] tag emitted by the model in the welcome message.
    // When found, the welcome was generated in the user's browser language, and the tag
    // holds the actual source document language (e.g. 'en' for an English PDF uploaded
    // by a Polish-speaking user). We set detectedLang to the browser language so
    // isTranslated stays false for the initial (untranslated) view.
    const langTagMatch = firstAssistant.content.match(/\[language\]([a-z]{2,3})\[\/language\]/i)
    if (langTagMatch) {
      sourceLang.value = langTagMatch[1].toLowerCase()
      // detectedLang = user's browser language (content was generated in that language)
      detectedLang.value = browserLang.value
      if (!currentLang.value) currentLang.value = browserLang.value

      if (storedLang && storedLang !== browserLang.value && currentLang.value !== storedLang) {
        await nextTick()
        translateTo(storedLang)
      }
      return
    }

    try {
      const result = await detectLanguage(firstAssistant.content)
      detectedLang.value = result.language
      sourceLang.value = result.language
      // Only reset currentLang to detected if we haven't already applied a stored translation
      if (!currentLang.value) currentLang.value = result.language

      // If stored lang differs from detected and wasn't already applied via cache, translate now
      if (storedLang && storedLang !== result.language && currentLang.value !== storedLang) {
        await nextTick()
        translateTo(storedLang)
      }
    } catch {
      detectionAttempted.value = false // allow retry on next message change
    }
  },
  { immediate: true, deep: true },
)

function onButtonClick() {
  // Clicking during an in-flight translation cancels the visual waiting state
  // but leaves the background request running (see spec: "do not cancel
  // previous translate request"). The guard inside translateTo() uses
  // pendingLang to decide whether to apply the result when it eventually
  // resolves — clearing pendingLang here suppresses apply for the prior
  // click, while the promise stays in inflightTranslations so the next click
  // on the same target can re-await it.
  if (translating.value && pendingLang.value) {
    pendingLang.value = ''
    translating.value = false
    emit('translating-end')
    return
  }

  if (isToggleMode.value) {
    // Two languages: toggle directly
    const other = availableLangs.value.find((l) => l !== currentLang.value)!
    translateTo(other)
    return
  }

  // Three+ languages: if currently translated, first click restores original
  if (isTranslated.value) {
    translateTo(detectedLang.value)
    return
  }

  // Show dropdown to pick target
  showDropdown.value = !showDropdown.value
}

// Translate messages that arrived after a translation was applied, back into
// the detected (original) language. Used by the restore path so messages the
// user typed in their chosen target language are displayed in the document's
// original language after toggling back.
async function translateNewMessagesBack(): Promise<Map<number, string>> {
  const result = new Map<number, string>()
  const toTranslateBack: { index: number; content: string; id?: string }[] = []

  // Bulk-load any stored back-translations up front so forEach stays sync.
  const candidateIds = props.messages
    .filter((m, i) => i > translatedUpToIndex.value && m.content.trim() && m.id)
    .map((m) => m.id!)
  const storedMap = await getBulkStoredTranslations(detectedLang.value, candidateIds)

  props.messages.forEach((msg, i) => {
    if (i <= translatedUpToIndex.value) return
    if (!msg.content.trim()) return
    const memKey = `${msg.content}→${detectedLang.value}`
    const mem = translationCache.value.get(memKey)
    if (mem) {
      result.set(i, mem)
      return
    }
    if (msg.id) {
      const stored = storedMap.get(msg.id)
      if (stored) {
        result.set(i, stored)
        translationCache.value.set(memKey, stored)
        return
      }
    }
    toTranslateBack.push({ index: i, content: msg.content, id: msg.id })
  })

  if (toTranslateBack.length) {
    const translated = await translateWithMarkers(
      toTranslateBack.map((c) => c.content),
      detectedLang.value,
      currentLang.value,
    )
    toTranslateBack.forEach((item, j) => {
      const t = translated.translations[j]
      if (!t) return
      result.set(item.index, t)
      translationCache.value.set(`${item.content}→${detectedLang.value}`, t)
      translationCache.value.set(`${t}→${currentLang.value}`, item.content)
      if (item.id) void setStoredTranslation(detectedLang.value, item.id, t)
    })
  }
  return result
}

// Build the translated payload (messages + title) for a foreign target.
// Uses in-memory and IndexedDB caches to skip messages already translated.
async function buildTranslation(targetLang: string): Promise<PendingTranslation> {
  const translations = new Map<number, string>()
  const toTranslate: { index: number; content: string; id?: string }[] = []

  // Bulk-load any stored translations for this target language up front.
  const candidateIds = props.messages
    .filter((m) => m.content.trim() && m.id && !translationCache.value.has(`${m.content}→${targetLang}`))
    .map((m) => m.id!)
  const storedMap = await getBulkStoredTranslations(targetLang, candidateIds)

  props.messages.forEach((msg, i) => {
    if (!msg.content.trim()) return
    const cacheKey = `${msg.content}→${targetLang}`
    const cached = translationCache.value.get(cacheKey)
    if (cached) {
      translations.set(i, cached)
      return
    }
    // Persisted per-message cache survives reload.
    if (msg.id) {
      const stored = storedMap.get(msg.id)
      if (stored) {
        translations.set(i, stored)
        translationCache.value.set(cacheKey, stored)
        return
      }
    }
    toTranslate.push({ index: i, content: msg.content, id: msg.id })
  })

  // Title is sent as a separate batch so callers can keep it in a dedicated
  // emit path; running both calls in parallel minimises perceived latency.
  const titleText = props.title?.trim() ?? ''
  const titleCacheKey = titleText ? `${titleText}→${targetLang}` : ''
  const titleCached = titleText ? translationCache.value.get(titleCacheKey) : undefined

  const jobs: Promise<void>[] = []

  if (toTranslate.length) {
    jobs.push(
      translateWithMarkers(
        toTranslate.map((c) => c.content),
        targetLang,
        detectedLang.value || undefined,
      ).then((result) => {
        toTranslate.forEach((item, j) => {
          const t = result.translations[j]
          if (t === undefined) return
          translations.set(item.index, t)
          translationCache.value.set(`${item.content}→${targetLang}`, t)
          if (item.id) void setStoredTranslation(targetLang, item.id, t)
        })
      }),
    )
  }

  let title: string | undefined = titleCached
  if (titleText && !titleCached) {
    jobs.push(
      translateWithMarkers([titleText], targetLang, detectedLang.value || undefined).then(
        (result) => {
          const t = result.translations[0]
          if (t) {
            title = t
            translationCache.value.set(titleCacheKey, t)
          }
        },
      ),
    )
  }

  await Promise.all(jobs)
  return { translations, title }
}

async function translateTo(targetLang: string) {
  showDropdown.value = false
  if (targetLang === currentLang.value && !pendingLang.value) return

  // Restoring to original (detected) language. The parent holds the
  // originalMessages map and can instantly restore already-translated
  // messages; we only need to translate messages that arrived during the
  // translated state back into the detected language.
  if (targetLang === detectedLang.value) {
    pendingLang.value = targetLang
    translating.value = true
    emit('translating-start')
    try {
      const newMsgTranslations = await translateNewMessagesBack()
      currentLang.value = detectedLang.value
      await storeLanguage(detectedLang.value)
      emit('restored', newMsgTranslations)
    } catch (err) {
      console.error('Translation failed:', err)
      currentLang.value = detectedLang.value
      await storeLanguage(detectedLang.value)
      emit('restored', new Map())
    } finally {
      pendingLang.value = ''
      translating.value = false
      emit('translating-end')
    }
    return
  }

  // Translating to a foreign target.
  pendingLang.value = targetLang
  translating.value = true
  emit('translating-start')

  // If we're in an already-translated state (different foreign target),
  // restore originals first so buildTranslation reads the original text.
  // We only do this flash when the view was already translated — not during
  // the pending state of a still-loading translation, so the spec's
  // "don't blank the text" rule still holds for the cancel/re-click path.
  if (isTranslated.value) {
    currentLang.value = detectedLang.value
    emit('restored', new Map())
    await nextTick()
  }

  // Reuse an in-flight promise for the same target if one exists. On settle
  // we remove it so the next click builds a fresh request (and picks up any
  // new messages that arrived after the promise started).
  let promise = inflightTranslations.get(targetLang)
  if (!promise) {
    promise = buildTranslation(targetLang)
    inflightTranslations.set(targetLang, promise)
    // Silence "unhandled rejection" on the cached promise reference — actual
    // consumers still see the error via their own `await promise` below, but
    // without this attach a rejection on the bare promise reference causes
    // Node to log an unhandled rejection when nobody happens to be awaiting.
    void promise
      .catch(() => {})
      .finally(() => {
        if (inflightTranslations.get(targetLang) === promise) {
          inflightTranslations.delete(targetLang)
        }
      })
  }

  try {
    const result = await promise
    // Guard: user may have cancelled (clicked back) or re-targeted before
    // the promise resolved. Only apply when the latest click still wants
    // this target.
    if (pendingLang.value !== targetLang) return

    if (result.title) emit('title-translated', result.title)
    translatedUpToIndex.value = props.messages.length - 1
    currentLang.value = targetLang
    await storeLanguage(targetLang)
    emit('translated', result.translations)
  } catch (err) {
    console.error('Translation failed:', err)
  } finally {
    if (pendingLang.value === targetLang) {
      pendingLang.value = ''
      translating.value = false
      emit('translating-end')
    }
  }
}

// Emit whenever the current display language changes (detection, translation, restore)
watch(currentLang, (lang) => {
  if (lang) emit('lang-changed', lang)
})

defineExpose({ detectedLang, isTranslated, currentLang, availableLangs })
</script>

<style scoped>
.lang-toggle-wrap {
  position: relative;
  display: inline-flex;
}

.lang-toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  padding: 5px 8px;
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
  transition:
    border-color 0.15s,
    background 0.15s;
  color: #e2e8f0;
}

@media (hover: hover) {
  .lang-toggle-btn:hover:not(:disabled) {
    border-color: #a78bfa;
    background: rgba(167, 139, 250, 0.1);
  }
}

.lang-toggle-btn:disabled {
  opacity: 0.7;
  cursor: wait;
}

.lang-flag.translating {
  opacity: 0.5;
}

.lang-spinner {
  animation: spin 1s linear infinite;
}

.lang-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  background: #1e1e2e;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 8px;
  padding: 4px 0;
  z-index: 100;
  min-width: 140px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
}

.lang-dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 12px;
  background: none;
  border: none;
  color: #e2e8f0;
  cursor: pointer;
  font-size: 14px;
  white-space: nowrap;
  transition: background 0.1s;
}

@media (hover: hover) {
  .lang-dropdown-item:hover {
    background: rgba(167, 139, 250, 0.15);
  }
}

@keyframes spin {
  100% {
    transform: rotate(360deg);
  }
}
</style>
