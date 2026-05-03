"""Fetch a web page and describe its content using the LLM.

Currently uses urllib for fetching raw HTML.
TODO: In future, use Playwright to render page with a real browser engine
for ~2s before capturing the fully-rendered DOM.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from html.parser import HTMLParser

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from .lang_detect import detect_language
from .llm_instrument import traced_llm_call
from .rag import get_llm

logger = logging.getLogger(__name__)

# Budget for HTML content sent to the model (chars)
_MAX_HTML_CHARS = 120_000

# Common user-agent to avoid being blocked
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class _TextExtractor(HTMLParser):
    """Minimal HTML→text converter: strips tags, keeps visible text.

    Keeps <title> content (useful for page identification and indexing) while
    still skipping scripts, styles and other non-visible head elements.
    """

    # Skip everything in <head> *except* the <title> element.
    # <meta> and <link> are self-closing with no visible text anyway, but
    # we include them explicitly to be safe.
    _SKIP_TAGS = {"script", "style", "noscript", "svg", "path", "meta", "link"}

    def __init__(self):
        super().__init__()
        self._pieces: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str):
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)

    def handle_data(self, data: str):
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self._pieces.append(text)

    def get_text(self) -> str:
        return "\n".join(self._pieces)


def _extract_visible_text(html: str) -> str:
    """Extract visible text content from HTML (strip tags, scripts, styles)."""
    parser = _TextExtractor()
    parser.feed(html)
    return parser.get_text()


def fetch_url(url: str, timeout: int = 15) -> str:
    """Fetch raw HTML from a URL. Returns the HTML string."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


_SYSTEM_PROMPT_PL = """Analizujesz kod źródłowy HTML strony internetowej tak, jak UŻYTKOWNIK widziałby tę stronę w przeglądarce.

KLUCZOWE NASTAWIENIE: Czytaj HTML jak człowiek przeglądający stronę — NIE jak programista. Tagi HTML (<div>, <span>, <p>, <h1>, <ul>, <li>, <table>, <strong>, <img alt="...">) to niewidzialne pojemniki strukturalne. Prawdziwa TREŚĆ to tekst między tagami, atrybuty alt obrazków, dane w JSON-LD i schema.org. Traktuj HTML jak tekst z niewidzialnym formatowaniem — wyciągnij ZNACZENIE, nie kod.

== INSTRUKCJA ODPOWIEDZI ==

1. **Tytuł** (pierwsza linia): Sformatuj jako: ## [Nazwa serwisu] — [czego dotyczy ta strona]
   Przykład: ## Allegro — Pharmovit Kolagen Włosy, Skóra, Paznokcie 500ml | Biotyna, MSM, Kwas Hialuronowy

2. **Główna treść** (2–4 akapity): Wyciągnij i przedstaw KLUCZOWE FAKTY, które użytkownik przeczytałby na stronie:

   - **Strony produktowe (sklep, e-commerce)**: pełna nazwa produktu, marka, WSZYSTKIE składniki (szczególnie suplementy/żywność — wymień każdy składnik z dawką!), wartości odżywcze, dawkowanie, cena, ocena, liczba opinii, kluczowe cechy, skład opakowania
     Przykład z HTML: `<h1>Kolagen Włosy 500ml</h1><ul><li>Kolagen rybny 5000mg</li><li>Biotyna 10mg</li><li>MSM 2000mg</li></ul><span>49,99 zł</span>`
     → Suplement w płynie **Kolagen Włosy 500ml** zawiera: **Kolagen rybny 5000mg**, **Biotyna 10mg**, **MSM 2000mg** — cena **49,99 zł**. Opinie: ⭐ 4,7 (328 opinii).

   - **Artykuły / newsy**: nagłówek, autor, data, główna teza, kluczowe fakty i liczby

   - **Przepisy kulinarne**: nazwa dania, PEŁNA lista składników z ilościami, czas przygotowania, liczba porcji

   - **Blogi / strony firmowe**: główny temat, kluczowe sekcje, cel strony

   - **Serwisy / oprogramowanie**: co robi usługa, funkcje, cennik, dla kogo jest przeznaczona

   - **Strony wiedzy (Wikipedia itp.)**: definicja tematu, kluczowe fakty, kontekst historyczny

3. **O czym możesz pytać** (1–2 zdania): Co użytkownik może wyciągnąć z tej strony.

WAŻNE: Wyciągaj konkretne dane (nazwy produktów, listy składników, ceny, opinie, fragmenty artykułów, tabele danych). NIE opisuj struktury HTML ("jest div z klasą..."). Pisz jak człowiek streszczający to, co właśnie przeczytał na stronie.

Używaj profesjonalnych emoji oszczędnie (🛒, 💊, 📊, 🧴, ✅, ⭐, 💡, 🔍) — najwyżej 2–3 w całej odpowiedzi.
Odpowiadaj w tym samym języku co treść strony.

Na końcu dodaj DOKŁADNIE 7 przycisków akcji na JEDNEJ LINII w tym formacie:
[action:Etykieta1] [action:Etykieta2] [action:Etykieta3] [action:Etykieta4] [action:Etykieta5] [action:Etykieta6] [action:Etykieta7]

Zasady przycisków:
- Przyciski 1–2: konkretne pytania uzupełniające BEZ emoji, dopasowane do treści strony
- Przyciski 3–7: akcje wzbogacone kończące się emoji, dobrane do typu strony:
  * Dla produktów: "Lista wszystkich składników ✅", "Porównaj z podobnymi produktami 🔍", "Stwórz checklistę zakupową 📋", "Analiza składu suplementu 💊", "Wygeneruj obraz inspirowany: [nazwa produktu] 🎨"
  * Dla artykułów: "Podsumuj kluczowe fakty 📊", "Stwórz quiz z artykułu 🧠", "Znajdź powiązane tematy 🔍"
  * Dla przepisów: "Lista zakupów z ilościami 🛒", "Instrukcja krok po kroku 📋", "Wygeneruj obraz inspirowany: [nazwa dania] 🎨"
  * Dla stron ogólnych: "Wygeneruj obraz inspirowany: [temat strony] 🎨", "Stwórz quiz z treści 🧠", "Stwórz mapę myśli 🧩"
WSZYSTKIE 7 przycisków MUSZĄ być w tym samym języku co treść strony.
Emoji 🎨 jest ZAREZERWOWANE WYŁĄCZNIE dla akcji generowania obrazu."""

_SYSTEM_PROMPT_EN = """You are analyzing the raw HTML source of a web page to understand what a visitor would see in their browser.

CRITICAL MINDSET: Read the HTML as if you are a human browsing this website — NOT as a programmer reading code. HTML tags like <div>, <span>, <p>, <h1>, <ul>, <li>, <table>, <strong>, <img alt="..."> are invisible structural containers. The actual CONTENT is the text between those tags, the link href values, the alt attributes on images, and data embedded as JSON-LD or schema.org structured data. Treat HTML like prose with invisible formatting — extract the MEANING, not the markup.

== RESPONSE INSTRUCTIONS ==

1. **Title heading** (first line): Format as: ## [Website / service / brand] — [what this specific page is about]
   Example: ## Allegro — Pharmovit Collagen Hair, Skin, Nails 500ml | Biotin, MSM, Hyaluronic Acid

2. **Main content** (2–4 paragraphs): Extract and present the KEY FACTS a visitor would actually read:

   - **Product pages (shop, e-commerce)**: exact product name, brand, ALL ingredients (especially for supplements/food — list every ingredient with dosage!), nutritional info, dosage instructions, price, rating, review count, key features
     Example from HTML: `<h1>Collagen Hair 500ml</h1><ul><li>Fish collagen 5000mg</li><li>Biotin 10mg</li><li>MSM 2000mg</li></ul><span>$19.99</span>`
     → Liquid supplement **Collagen Hair 500ml** contains: **Fish collagen 5000mg**, **Biotin 10mg**, **MSM 2000mg** — priced at **$19.99**. Rated ⭐ 4.7 (328 reviews).

   - **News / articles**: headline, author, date, main argument, key facts and figures

   - **Recipe pages**: dish name, FULL ingredient list with quantities, prep time, servings

   - **Blog / company pages**: main topic, key sections, purpose of the page

   - **Service / software pages**: what the service does, features, pricing plans, target audience

   - **Knowledge pages (Wikipedia etc.)**: topic definition, key facts, historical context

3. **What you can ask about this page** (1–2 sentences): Brief guide to what questions can be answered.

FOCUS: Extract the actual data (product names, ingredient lists, prices, reviews, article text, facts, data tables). Do NOT describe HTML structure ("there is a div with class..."). Write like a human summarizing what they just read on the website.

Use professional emoji sparingly (🛒, 💊, 📊, 🧴, ✅, ⭐, 💡, 🔍) — at most 2–3 total.
Reply in the same language as the page content.
Be thorough for ingredient/specification pages — list ALL items, not just some.

After the main content, add EXACTLY 7 follow-up action buttons on ONE LINE:
[action:Label1] [action:Label2] [action:Label3] [action:Label4] [action:Label5] [action:Label6] [action:Label7]

Button rules:
- Buttons 1–2: plain follow-up questions specific to this page's content (NO emoji)
- Buttons 3–7: rich actions ending with emoji, tailored to this page type:
  * For products: "List all ingredients ✅", "Compare with similar products 🔍", "Create shopping checklist 📋", "Supplement ingredient analysis 💊", "Generate image inspired by: [product name] 🎨"
  * For articles: "Summarize key facts 📊", "Create a quiz from this article 🧠", "Find related topics 🔍"
  * For recipes: "Shopping list with quantities 🛒", "Step-by-step instructions 📋", "Generate image inspired by: [dish name] 🎨"
  * For general pages: "Generate image inspired by: [page topic] 🎨", "Create a quiz from this content 🧠", "Create a mind map 🧩"
ALL 7 buttons MUST be in the same language as the page content.
🎨 is RESERVED EXCLUSIVELY for image-generation actions."""


def describe_url(url: str, html: str, language: str | None = None) -> str:
    """Generate a welcome message describing a web page from its HTML."""
    # Extract visible text for language detection
    visible_text = _extract_visible_text(html)

    if language is None:
        language = detect_language(visible_text[:2000])

    # Truncate HTML to budget
    html_truncated = html[:_MAX_HTML_CHARS]

    system_prompt = _SYSTEM_PROMPT_PL if language == "pl" else _SYSTEM_PROMPT_EN
    human_prompt = (
        "Cel: opisz co jest na stronie internetowej na podstawie HTML\nURL: {url}\n\nHTML:\n{html}"
        if language == "pl"
        else "Goal: describe what is on this web page by reading the HTML as a user would see it\nURL: {url}\n\nHTML:\n{html}"
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", human_prompt),
        ]
    )

    llm = get_llm()
    chain = prompt | llm | StrOutputParser()
    model = getattr(llm, "model", None) or getattr(llm, "model_name", None) or "unknown"
    result, _usage = traced_llm_call(
        chain=chain,
        params={"url": url, "html": html_truncated},
        operation="url_describe",
        model=model,
    )
    return result.strip()
