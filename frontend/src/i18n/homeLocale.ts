/**
 * Home page i18n.
 *
 * Keeps the language selection for static home-page chrome (hero subtitle,
 * dropzone hints, ask-a-question placeholder, upload errors) independent of
 * the conversation translation flow handled by `LanguageToggle.vue`.
 *
 * - On first visit, the language follows the browser (pl → 'pl', else 'en').
 * - The user can override via the home-page flag toggle; the choice is
 *   persisted in IndexedDB and restored on subsequent loads.
 */
import { computed, ref } from 'vue'
import { ConfigurationsTable } from '../utils/database'

export type HomeLang = 'en' | 'pl'

export const HOME_LANG_KEY = 'homePageLang'
const SUPPORTED: readonly HomeLang[] = ['en', 'pl'] as const

function isSupported(value: unknown): value is HomeLang {
  return value === 'en' || value === 'pl'
}

function browserDefaultLang(): HomeLang {
  const browser =
    typeof navigator !== 'undefined' && navigator.language ? navigator.language.toLowerCase() : 'en'
  return browser.startsWith('pl') ? 'pl' : 'en'
}

// Start with browser default; updated from IndexedDB by initHomeLang() at app startup.
export const homeLang = ref<HomeLang>(browserDefaultLang())

/** Load persisted home language from IndexedDB. Call once at app startup, after initDatabase(). */
export async function initHomeLang(): Promise<void> {
  try {
    const saved = await ConfigurationsTable.get<string>(HOME_LANG_KEY)
    if (isSupported(saved)) homeLang.value = saved
  } catch {
    // Non-fatal; browser default stays active.
  }
}

export async function setHomeLang(lang: HomeLang): Promise<void> {
  if (!SUPPORTED.includes(lang)) return
  homeLang.value = lang
  try {
    await ConfigurationsTable.set(HOME_LANG_KEY, lang)
  } catch {
    // Ignore storage errors (e.g. quota exceeded, private mode).
  }
}

export function toggleHomeLang(): void {
  void setHomeLang(homeLang.value === 'pl' ? 'en' : 'pl')
}

export interface HomeMessages {
  /** First subtitle paragraph; may contain inline HTML. */
  subtitleP1Html: string
  /** Second subtitle line, sits between P1 and P2; may contain inline HTML. */
  subtitleP1bHtml: string
  /** Third subtitle paragraph; contains <strong> for the AI Agent emphasis. */
  subtitleP2Html: string
  /** Fourth subtitle line (desktop); translate + synthesize speech + share answers. */
  subtitleP2bHtml: string
  /** Mobile-only: first line — search & RAG + translate files to your language. */
  subtitleP2MobileLine1Html: string
  /** Mobile-only: second line — synthesize speech + share answers. */
  subtitleP2MobileLine2Html: string
  /** Comma-separated capabilities line under the subtitle. */
  subtitleP3: string
  dropzoneHeading: string
  dropzoneTitle: string
  dropzoneHint: string
  askPlaceholder: string
  viewerReplyPlaceholder: string
  videoNotSupported: string
  fileTooLarge: string
  urlLoadFailed: string
  imageGenError: string
  switchTitle: string
}

export const homeMessages: Record<HomeLang, HomeMessages> = {
  en: {
    subtitleP1Html:
      "Upload your big PDFs and files privately 🔒",
    subtitleP1bHtml:
      'let AI present expert insights and learn to tell you what\u2019s inside files in each author\u2019s voices.',
    subtitleP2Html:
      'Ask prompt to <strong> AI Agent chatbot</strong>, do research, use semantic search & RAG,',
    subtitleP2bHtml:
      'translate files to your language 🇵🇱🇬🇧🌍 synthesize speech 🔊 share answers',
    subtitleP2MobileLine1Html:
      'Ask prompt to <strong> AI Agent chatbot</strong>, do research, use semantic search &amp; RAG, translate files to your language 🇵🇱🇬🇧🌍',
    subtitleP2MobileLine2Html: 'synthesize speech 🔊 share answers',
    subtitleP3:
      'Generate image 🎨 book chapter 📖 poem 📜 diagnosis 🔬 interactive quiz 🧠 quote 💬 PDF 📄 mermaid diagram 💡 recipe 🍝 checklist ✅ and more!',
    dropzoneHeading: 'Upload',
    dropzoneTitle: 'click or drag & drop',
    dropzoneHint: 'PDF, DOCX, PPTX, images, URL, other text files',
    askPlaceholder: 'Ask your question ...',
    viewerReplyPlaceholder: 'Reply to start your own thread ...',
    videoNotSupported: 'Video files are not supported.',
    fileTooLarge: 'File too large. Maximum upload size is ~30 MB per file.',
    urlLoadFailed: 'Failed to load URL',
    imageGenError: 'Sorry, there was an error during generating image. Refresh page or try again.',
    switchTitle: 'Switch home page language',
  },
  pl: {
    subtitleP1Html:
      'Wgraj swoje duże PDF-y i pliki bezpiecznie 🔒',
    subtitleP1bHtml:
      'pozwól AI przedstawić eksperckie wnioski i nauczyć się opowiadać co jest w plikach, głosem autorów.',
    subtitleP2Html:
      'Zadaj pytanie <strong> chatbotowi AI</strong>, rób research, używając wyszukiwania semantycznego i RAG,',
    subtitleP2bHtml:
      'tłumacz pliki na polski lub angielski 🇵🇱🇬🇧🌍 syntetyzuj mowę 🔊 udostępniaj odpowiedzi',
    subtitleP2MobileLine1Html:
      'Zadaj pytanie <strong> chatbotowi AI</strong>, rób research, używając wyszukiwania semantycznego i RAG, tłumacz pliki na polski lub angielski 🇵🇱🇬🇧🌍',
    subtitleP2MobileLine2Html: 'syntetyzuj mowę 🔊 udostępniaj odpowiedzi',
    subtitleP3:
      'Wygeneruj obraz 🎨 rozdział książki 📖 wiersz 📜 diagnozę 🔬 interaktywny quiz 🧠 cytat 💡 PDF 📄 diagram mermaid 🧩 przepis 🍝 checklistę ✅ i więcej!',
    dropzoneHeading: 'Prześlij',
    dropzoneTitle: 'kliknij lub przeciągnij i upuść',
    dropzoneHint: 'PDF, DOCX, PPTX, obrazy, URL, inne pliki tekstowe',
    askPlaceholder: 'Zadaj swoje pytanie ...',
    viewerReplyPlaceholder: 'Odpowiedz, aby rozpocząć własny wątek ...',
    videoNotSupported: 'Pliki wideo nie są obsługiwane.',
    fileTooLarge: 'Plik zbyt duży. Maksymalny rozmiar to ~30 MB na plik.',
    urlLoadFailed: 'Nie udało się wczytać URL',
    imageGenError: 'Przepraszam, wystąpił błąd podczas generowania obrazu. Odśwież stronę lub spróbuj ponownie.',
    switchTitle: 'Zmień język strony głównej',
  },
}

export const homeT = computed<HomeMessages>(() => homeMessages[homeLang.value])
