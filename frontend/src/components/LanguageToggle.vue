<template>
  <div v-if="detectedLang && availableLangs.length > 1" ref="wrapRef" class="lang-toggle-wrap">
    <button
      class="lang-toggle-btn"
      :title="translating ? 'Translating…' : buttonTitle"
      :disabled="translating"
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

// Marker handling for translation:
// - [source:N] markers are fully opaque (numeric id, must not change)
// - [action:Label] markers are also opaque during translation, but their Label
//   text is translated separately and re-inserted so suggested-action buttons
//   appear in the target language.
const MARKER_RE = /\[(source|action):([^\]]*)\]/gi

type MarkerInfo = {
  placeholder: string
  kind: 'source' | 'action'
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
    const result = text.replace(MARKER_RE, (match, kind: string, inner: string) => {
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

function restoreMarkers(
  translations: string[],
  markers: Map<number, MarkerInfo[]>,
): string[] {
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

async function translateActionLabels(
  markers: Map<number, MarkerInfo[]>,
  targetLang: string,
  sourceLang?: string,
) {
  // Collect unique action labels across all messages, then translate once and
  // write the translated label back onto every marker instance.
  const unique = new Map<string, MarkerInfo[]>()
  for (const list of markers.values()) {
    for (const info of list) {
      if (info.kind !== 'action' || !info.label) continue
      const existing = unique.get(info.label)
      if (existing) existing.push(info)
      else unique.set(info.label, [info])
    }
  }
  if (!unique.size) return
  const labels = [...unique.keys()]
  const translated: string[] = []
  for (let batch = 0; batch < labels.length; batch += 20) {
    const chunk = labels.slice(batch, batch + 20)
    const result = await translateTexts(chunk, targetLang, sourceLang)
    translated.push(...result.translations)
  }
  labels.forEach((label, i) => {
    const t = translated[i]
    if (!t) return
    for (const info of unique.get(label)!) info.label = t
  })
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
  const [result] = await Promise.all([
    translateTexts(stripped, targetLang, sourceLang),
    translateActionLabels(markers, targetLang, sourceLang),
  ])
  result.translations = result.translations.map((t, i) => leading[i] + t + trailing[i])
  result.translations = restoreMarkers(result.translations, markers)
  return result
}

const props = defineProps<{
  messages: Array<{ role: string; content: string }>
  suggestedQuestions?: string[]
  title?: string
  conversationId?: string
}>()

const emit = defineEmits<{
  translated: [translations: Map<number, string>]
  'questions-translated': [translations: string[]]
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
  if (translating.value) return

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

async function translateTo(targetLang: string) {
  showDropdown.value = false
  if (translating.value) return
  if (targetLang === currentLang.value) return

  // Restoring to original (detected) language
  if (targetLang === detectedLang.value) {
    pendingLang.value = targetLang
    translating.value = true
    emit('translating-start')
    try {
      const newMsgTranslations = new Map<number, string>()
      const toTranslateBack: { index: number; content: string }[] = []

      props.messages.forEach((msg, i) => {
        if (i <= translatedUpToIndex.value) return
        if (!msg.content.trim()) return
        const cached = translationCache.value.get(`${msg.content}→${detectedLang.value}`)
        if (cached) {
          newMsgTranslations.set(i, cached)
        } else {
          toTranslateBack.push({ index: i, content: msg.content })
        }
      })

      for (let batch = 0; batch < toTranslateBack.length; batch += 20) {
        const chunk = toTranslateBack.slice(batch, batch + 20)
        const result = await translateWithMarkers(
          chunk.map((c) => c.content),
          detectedLang.value,
          currentLang.value,
        )
        chunk.forEach((item, j) => {
          const translated = result.translations[j]
          newMsgTranslations.set(item.index, translated)
          translationCache.value.set(`${item.content}→${detectedLang.value}`, translated)
          translationCache.value.set(`${translated}→${currentLang.value}`, item.content)
        })
      }

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

  // Translating to a new target language
  // If currently showing a translation, restore first then translate
  const _sourceLang = currentLang.value
  pendingLang.value = targetLang
  translating.value = true
  emit('translating-start')
  try {
    // If we're in a translated state, restore originals first
    if (isTranslated.value) {
      currentLang.value = detectedLang.value
      emit('restored', new Map())
      // Small tick to let parent restore originals
      await new Promise((r) => setTimeout(r, 0))
    }

    const translations = new Map<number, string>()
    const toTranslate: { index: number; content: string }[] = []

    props.messages.forEach((msg, i) => {
      if (!msg.content.trim()) return
      const cacheKey = `${msg.content}→${targetLang}`
      const cached = translationCache.value.get(cacheKey)
      if (cached) {
        translations.set(i, cached)
      } else {
        toTranslate.push({ index: i, content: msg.content })
      }
    })

    for (let batch = 0; batch < toTranslate.length; batch += 20) {
      const chunk = toTranslate.slice(batch, batch + 20)
      const result = await translateWithMarkers(
        chunk.map((c) => c.content),
        targetLang,
        detectedLang.value,
      )
      chunk.forEach((item, j) => {
        translations.set(item.index, result.translations[j])
        translationCache.value.set(`${item.content}→${targetLang}`, result.translations[j])
      })
    }

    // Translate suggested questions
    const questions = props.suggestedQuestions || []
    if (questions.length) {
      const qToTranslate: { index: number; text: string }[] = []
      const qTranslated: string[] = []
      questions.forEach((q, i) => {
        const cacheKey = `${q}→${targetLang}`
        const cached = translationCache.value.get(cacheKey)
        if (cached) {
          qTranslated[i] = cached
        } else {
          qToTranslate.push({ index: i, text: q })
        }
      })
      for (let batch = 0; batch < qToTranslate.length; batch += 20) {
        const chunk = qToTranslate.slice(batch, batch + 20)
        const result = await translateWithMarkers(
          chunk.map((c) => c.text),
          targetLang,
          detectedLang.value,
        )
        chunk.forEach((item, j) => {
          qTranslated[item.index] = result.translations[j]
          translationCache.value.set(`${item.text}→${targetLang}`, result.translations[j])
        })
      }
      emit('questions-translated', qTranslated)
    }

    // Translate conversation title (emitted separately so caller can restore it)
    const title = props.title?.trim()
    if (title) {
      const cacheKey = `${title}→${targetLang}`
      const cached = translationCache.value.get(cacheKey)
      if (cached) {
        emit('title-translated', cached)
      } else {
        const result = await translateWithMarkers([title], targetLang, detectedLang.value)
        const translated = result.translations[0]
        if (translated) {
          translationCache.value.set(cacheKey, translated)
          emit('title-translated', translated)
        }
      }
    }

    translatedUpToIndex.value = props.messages.length - 1
    currentLang.value = targetLang
    storeLanguage(targetLang)
    emit('translated', translations)
  } catch (err) {
    console.error('Translation failed:', err)
  } finally {
    pendingLang.value = ''
    translating.value = false
    emit('translating-end')
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
