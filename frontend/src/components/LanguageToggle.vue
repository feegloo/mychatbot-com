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
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import ISO6391 from 'iso-639-1'
import { translateTexts, detectLanguage } from '../api'
import { getStoredTranslation, setStoredTranslation } from '../utils/translationStorage'

// Marker handling for translation:
// - [source:N] markers are fully opaque (numeric id, must not change)
// - [action:Label] markers are also opaque during translation, but their Label
//   text is translated separately and re-inserted so suggested-action buttons
//   appear in the target language.
// - [poem] / [/poem] tags are opaque so the literal word "poem" isn't
//   translated (e.g. to "wiersz" in Polish), while the verse content between
//   the tags is still translated naturally as part of the surrounding text.
// - ![alt](url) markdown images are opaque: the URL must never be translated
//   (e.g. Pollinations URLs embed the prompt in the path, and translating it
//   produces an unreachable src and a broken-image icon after the v-html swap).
const MARKER_RE = /\[(source|action):([^\]]*)\]/gi
const POEM_TAG_RE = /\[\/?poem\]/gi
// Markdown image: `![alt](url "optional title")`. Uses negated character
// classes so the match stops at the first closing `]` / `)` rather than
// spanning over adjacent links on the same line.
const IMAGE_MD_RE = /!\[[^\]]*\]\([^)\s]+(?:\s+"[^"]*")?\)/g

type MarkerInfo = {
  placeholder: string
  kind: 'source' | 'action' | 'image' | 'poem'
  original: string
  label?: string // only for action markers; gets replaced with translated label
}

function extractMarkers(texts: string[]): {
  cleaned: string[]
  markers: Map<number, MarkerInfo[]>
} {
  const markers = new Map<number, MarkerInfo[]>()
  const cleaned = texts.map((text, i) => {
    const found: MarkerInfo[] = []
    let counter = 0
    // Extract markdown images first so their `[alt]` brackets don't collide
    // with the [source:…]/[action:…] marker regex on the following pass.
    let result = text.replace(IMAGE_MD_RE, (match) => {
      const placeholder = `__MRK${i}_${counter++}__`
      found.push({ placeholder, kind: 'image', original: match })
      return placeholder
    })
    result = result.replace(POEM_TAG_RE, (match) => {
      const placeholder = `__MRK${i}_${counter++}__`
      found.push({ placeholder, kind: 'poem', original: match })
      return placeholder
    })
    result = result.replace(MARKER_RE, (match, kind: string, inner: string) => {
      const placeholder = `__MRK${i}_${counter++}__`
      const info: MarkerInfo = {
        placeholder,
        kind: kind.toLowerCase() === 'action' ? 'action' : 'source',
        original: match,
      }
      if (info.kind === 'action') info.label = inner.trim()
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
          ? `[action:${info.label}]`
          : info.original
      result = result.replace(info.placeholder, replacement)
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

const CONV_LANG_KEY = 'conversation-languages'

function getStoredLanguage(): string | null {
  if (!props.conversationId) return null
  try {
    const stored = localStorage.getItem(CONV_LANG_KEY)
    const map = stored ? JSON.parse(stored) : {}
    return map[props.conversationId] || null
  } catch {
    return null
  }
}

function storeLanguage(lang: string) {
  if (!props.conversationId) return
  try {
    const stored = localStorage.getItem(CONV_LANG_KEY)
    const map = stored ? JSON.parse(stored) : {}
    if (lang === detectedLang.value) {
      delete map[props.conversationId]
    } else {
      map[props.conversationId] = lang
    }
    localStorage.setItem(CONV_LANG_KEY, JSON.stringify(map))
  } catch {
    /* ignore */
  }
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

// Available target languages: unique set of {detected, browser, 'en'} minus current
const availableLangs = computed(() => {
  const set = new Set<string>()
  if (detectedLang.value) set.add(detectedLang.value)
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
    try {
      const result = await detectLanguage(firstAssistant.content)
      detectedLang.value = result.language
      currentLang.value = result.language

      // Auto-translate if there's a stored language preference different from detected
      const storedLang = getStoredLanguage()
      if (storedLang && storedLang !== result.language) {
        // Defer to next tick so the component is fully rendered
        await new Promise((r) => setTimeout(r, 50))
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
      const stored = getStoredTranslation(detectedLang.value, msg.id)
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
      if (item.id) setStoredTranslation(detectedLang.value, item.id, t)
    })
  }
  return result
}

// Build the translated payload (messages + title) for a foreign target.
// Uses in-memory and localStorage caches to skip messages already translated.
async function buildTranslation(targetLang: string): Promise<PendingTranslation> {
  const translations = new Map<number, string>()
  const toTranslate: { index: number; content: string; id?: string }[] = []

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
      const stored = getStoredTranslation(targetLang, msg.id)
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
          if (item.id) setStoredTranslation(targetLang, item.id, t)
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
      storeLanguage(detectedLang.value)
      emit('restored', newMsgTranslations)
    } catch (err) {
      console.error('Translation failed:', err)
      currentLang.value = detectedLang.value
      storeLanguage(detectedLang.value)
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
    await new Promise((r) => setTimeout(r, 0))
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
    storeLanguage(targetLang)
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
  padding: 4px 8px;
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
