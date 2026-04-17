<template>
  <button
    v-if="detectedLang && detectedLang !== browserLang"
    class="lang-toggle-btn"
    :title="translating ? 'Translating…' : (isTranslated ? `Showing ${langName(browserLang)} — click for original` : `Showing original (${langName(detectedLang)}) — click to translate`)"
    @click="toggle"
    :disabled="translating"
  >
    <span class="lang-flag" :class="{ translating }">{{ currentFlag }}</span>
    <svg v-if="translating" class="lang-spinner" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
  </button>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { translateTexts, detectLanguage } from "../api";

// Protect special markers like [source:1], [action:...] from being translated
const MARKER_RE = /\[(source|action):[^\]]*\]/gi;

function extractMarkers(texts: string[]): { cleaned: string[]; markers: Map<number, { placeholder: string; original: string }[]> } {
  const markers = new Map<number, { placeholder: string; original: string }[]>();
  const cleaned = texts.map((text, i) => {
    const found: { placeholder: string; original: string }[] = [];
    let counter = 0;
    const result = text.replace(MARKER_RE, (match) => {
      const placeholder = `__MRK${i}_${counter++}__`;
      found.push({ placeholder, original: match });
      return placeholder;
    });
    if (found.length) markers.set(i, found);
    return result;
  });
  return { cleaned, markers };
}

function restoreMarkers(translations: string[], markers: Map<number, { placeholder: string; original: string }[]>): string[] {
  return translations.map((text, i) => {
    const m = markers.get(i);
    if (!m) return text;
    let result = text;
    for (const { placeholder, original } of m) {
      result = result.replace(placeholder, original);
    }
    return result;
  });
}

async function translateWithMarkers(texts: string[], targetLang: string, sourceLang?: string) {
  const { cleaned, markers } = extractMarkers(texts);
  const result = await translateTexts(cleaned, targetLang, sourceLang);
  result.translations = restoreMarkers(result.translations, markers);
  return result;
}

const props = defineProps<{
  messages: Array<{ role: string; content: string }>;
  suggestedQuestions?: string[];
}>();

const emit = defineEmits<{
  translated: [translations: Map<number, string>];
  'questions-translated': [translations: string[]];
  restored: [newTranslations: Map<number, string>];
}>();

const detectedLang = ref("");
const browserLang = ref(navigator.language.split("-")[0]);
const isTranslated = ref(false);
const translating = ref(false);
const translationCache = ref<Map<string, string>>(new Map());
const detectionAttempted = ref(false);
const translatedUpToIndex = ref(-1); // tracks message count at time of last forward translation

const LANG_FLAGS: Record<string, string> = {
  en: "🇬🇧", pl: "🇵🇱", de: "🇩🇪", fr: "🇫🇷", es: "🇪🇸", it: "🇮🇹",
  pt: "🇵🇹", nl: "🇳🇱", ru: "🇷🇺", uk: "🇺🇦", cs: "🇨🇿", sk: "🇸🇰",
  ja: "🇯🇵", ko: "🇰🇷", zh: "🇨🇳", ar: "🇸🇦", hi: "🇮🇳", tr: "🇹🇷",
  sv: "🇸🇪", da: "🇩🇰", fi: "🇫🇮", no: "🇳🇴", hu: "🇭🇺", ro: "🇷🇴",
  bg: "🇧🇬", hr: "🇭🇷", el: "🇬🇷", he: "🇮🇱", th: "🇹🇭", vi: "🇻🇳",
  id: "🇮🇩", ms: "🇲🇾",
};

const LANG_NAMES: Record<string, string> = {
  en: "English", pl: "Polish", de: "German", fr: "French", es: "Spanish",
  it: "Italian", pt: "Portuguese", nl: "Dutch", ru: "Russian", uk: "Ukrainian",
  cs: "Czech", sk: "Slovak", ja: "Japanese", ko: "Korean", zh: "Chinese",
  ar: "Arabic", hi: "Hindi", tr: "Turkish", sv: "Swedish", da: "Danish",
  fi: "Finnish", no: "Norwegian", hu: "Hungarian", ro: "Romanian", bg: "Bulgarian",
  hr: "Croatian", el: "Greek", he: "Hebrew", th: "Thai", vi: "Vietnamese",
  id: "Indonesian", ms: "Malay",
};

function langName(code: string) {
  return LANG_NAMES[code] || code;
}

const currentFlag = computed(() => {
  const lang = isTranslated.value ? browserLang.value : detectedLang.value;
  return LANG_FLAGS[lang] || "🌐";
});

// Detect language from first assistant message (retries until successful)
watch(() => props.messages, async (msgs) => {
  if (detectedLang.value || detectionAttempted.value) return;
  const firstAssistant = msgs.find(m => m.role === "assistant" && m.content.length > 20);
  if (!firstAssistant) return;
  detectionAttempted.value = true;
  try {
    const result = await detectLanguage(firstAssistant.content);
    detectedLang.value = result.language;
  } catch {
    detectionAttempted.value = false; // allow retry on next message change
  }
}, { immediate: true, deep: true });

async function toggle() {
  if (translating.value) return;

  if (isTranslated.value) {
    // Restoring to original/detected language
    translating.value = true;
    try {
      // Translate messages added while in translated state (browserLang → detectedLang)
      const newMsgTranslations = new Map<number, string>();
      const toTranslateBack: { index: number; content: string }[] = [];

      props.messages.forEach((msg, i) => {
        if (i <= translatedUpToIndex.value) return; // part of original batch, parent restores these
        if (!msg.content.trim()) return;
        const cached = translationCache.value.get(msg.content);
        if (cached) {
          newMsgTranslations.set(i, cached);
        } else {
          toTranslateBack.push({ index: i, content: msg.content });
        }
      });

      // Translate new messages from browserLang to detectedLang
      for (let batch = 0; batch < toTranslateBack.length; batch += 20) {
        const chunk = toTranslateBack.slice(batch, batch + 20);
        const result = await translateWithMarkers(
          chunk.map(c => c.content),
          detectedLang.value,
          browserLang.value
        );
        chunk.forEach((item, j) => {
          const translated = result.translations[j];
          newMsgTranslations.set(item.index, translated);
          // Cache both directions for future toggles
          translationCache.value.set(item.content, translated);
          translationCache.value.set(translated, item.content);
        });
      }

      isTranslated.value = false;
      emit("restored", newMsgTranslations);
    } catch (err) {
      console.error("Translation failed:", err);
      isTranslated.value = false;
      emit("restored", new Map());
    } finally {
      translating.value = false;
    }
    return;
  }

  translating.value = true;
  try {
    const translations = new Map<number, string>();
    const toTranslate: { index: number; content: string }[] = [];

    // Check cache first, collect untranslated
    props.messages.forEach((msg, i) => {
      if (!msg.content.trim()) return;
      const cached = translationCache.value.get(msg.content);
      if (cached) {
        translations.set(i, cached);
      } else {
        toTranslate.push({ index: i, content: msg.content });
      }
    });

    // Translate in batches of 20
    for (let batch = 0; batch < toTranslate.length; batch += 20) {
      const chunk = toTranslate.slice(batch, batch + 20);
      const result = await translateWithMarkers(
        chunk.map(c => c.content),
        browserLang.value,
        detectedLang.value
      );
      chunk.forEach((item, j) => {
        translations.set(item.index, result.translations[j]);
        translationCache.value.set(item.content, result.translations[j]);
      });
    }

    // Translate suggested questions
    const questions = props.suggestedQuestions || [];
    if (questions.length) {
      const qToTranslate: { index: number; text: string }[] = [];
      const qTranslated: string[] = [];
      questions.forEach((q, i) => {
        const cached = translationCache.value.get(q);
        if (cached) {
          qTranslated[i] = cached;
        } else {
          qToTranslate.push({ index: i, text: q });
        }
      });
      for (let batch = 0; batch < qToTranslate.length; batch += 20) {
        const chunk = qToTranslate.slice(batch, batch + 20);
        const result = await translateWithMarkers(
          chunk.map(c => c.text),
          browserLang.value,
          detectedLang.value
        );
        chunk.forEach((item, j) => {
          qTranslated[item.index] = result.translations[j];
          translationCache.value.set(item.text, result.translations[j]);
        });
      }
      emit("questions-translated", qTranslated);
    }

    translatedUpToIndex.value = props.messages.length - 1;
    isTranslated.value = true;
    emit("translated", translations);
  } catch (err) {
    console.error("Translation failed:", err);
  } finally {
    translating.value = false;
  }
}

defineExpose({ detectedLang, isTranslated });
</script>

<style scoped>
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
  transition: border-color 0.15s, background 0.15s;
  color: #e2e8f0;
}

.lang-toggle-btn:hover:not(:disabled) {
  border-color: #a78bfa;
  background: rgba(167, 139, 250, 0.1);
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

@keyframes spin {
  100% { transform: rotate(360deg); }
}
</style>
