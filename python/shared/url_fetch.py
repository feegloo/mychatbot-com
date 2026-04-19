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
    """Minimal HTML→text converter: strips tags, keeps visible text."""

    _SKIP_TAGS = {"script", "style", "noscript", "svg", "path", "meta", "link", "head"}

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


def describe_url(url: str, html: str, language: str | None = None) -> str:
    """Generate a welcome message describing a web page from its HTML."""
    # Extract visible text for language detection
    visible_text = _extract_visible_text(html)

    if language is None:
        language = detect_language(visible_text[:2000])

    # Truncate HTML to budget
    html_truncated = html[:_MAX_HTML_CHARS]

    if language == "pl":
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """Twoim zadaniem jest opisanie strony internetowej na podstawie jej kodu HTML.
Przeanalizuj strukturę HTML i treść, aby zrozumieć co znajduje się na stronie.

Twoja odpowiedź MUSI składać się z trzech części:

1. **Tytuł** (pierwsza linia): Nazwa strony/serwisu i krótki opis.
   Sformatuj jako nagłówek Markdown: ## Tytuł tutaj

2. **Opis** (po tytule): 2-4 zdania opisujące zawartość strony. Wymień najważniejsze sekcje, artykuły, tematy, produkty lub usługi widoczne na stronie. Używaj **pogrubienia** dla kluczowych elementów.

3. **Ekspercki wgląd** (po opisie): 2-3 zdania z obserwacjami na temat strony — np. typ strony (portal, sklep, blog, landing page), główny cel, docelowa grupa odbiorców, jakość treści.

Skup się na TREŚCI strony, nie na kodzie HTML.
Pisz jak człowiek opisujący stronę innemu człowiekowi.
Bądź zwięzły. NIE pytaj użytkownika o nic.
Używaj profesjonalnych emoji (🌐, 📰, 🛒, 📊, 💡, 🔍) oszczędnie.
Odpowiadaj po polsku.""",
                ),
                (
                    "human",
                    "Cel: opisz co znajduje się na stronie internetowej na podstawie HTML\nURL: {url}\n\nHTML:\n{html}",
                ),
            ]
        )
    else:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """Your task is to describe a website by inspecting its HTML code.
Analyze the HTML structure and content to understand what is on the page.

Your response MUST have three parts:

1. **Title** (first line): The website/service name and a short description.
   Format as a Markdown heading: ## Title here

2. **Description** (after the title): 2-4 sentences describing the page content. Mention the most important sections, articles, topics, products, or services visible on the page. Use **bold** for key elements.

3. **Expert insight** (after the description): 2-3 sentences with observations about the page — e.g. the type of site (portal, e-commerce, blog, landing page), main purpose, target audience, content quality.

Focus on the CONTENT of the page, not the HTML code itself.
Write like a human describing a website to another human.
Be concise. Do NOT ask the user anything.
Use professional emoji (🌐, 📰, 🛒, 📊, 💡, 🔍) sparingly.
Reply in the same language as the page content.""",
                ),
                (
                    "human",
                    "Goal: describe what is on website by inspecting HTML\nURL: {url}\n\nHTML:\n{html}",
                ),
            ]
        )

    llm = get_llm()
    chain = prompt | llm | StrOutputParser()
    result = chain.invoke({"url": url, "html": html_truncated})
    return result.strip()
