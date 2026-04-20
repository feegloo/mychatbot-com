from __future__ import annotations

import json
import logging
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from .extractors import clean_file_name
from .lang_detect import detect_language
from .llm_instrument import traced_llm_call
from .rag import get_llm

logger = logging.getLogger(__name__)

_QUESTIONS_SEPARATOR = "---SUGGESTED_QUESTIONS---"
_PAGE_HEADER_RE = re.compile(r"^#\s*Page\s+(\d+)\s*$", re.MULTILINE)


class DescribeResult(TypedDict):
    welcome_message: str
    suggested_questions: list[str]


def _fallback_from_metadata(
    extracted: list[dict],
    images: list[dict],
    file_metadata: dict[str, dict] | None,
    language: str | None,
) -> str:
    """Generate a minimal welcome message when no text could be extracted."""
    file_names = [clean_file_name(doc.get("file_name", "")) for doc in extracted]
    file_names += [clean_file_name(img.get("file_name", "")) for img in images]
    name_list = ", ".join(dict.fromkeys(fn for fn in file_names if fn)) or "document"

    title_from_meta = ""
    if file_metadata:
        for meta in file_metadata.values():
            if isinstance(meta, dict) and meta.get("title"):
                title_from_meta = meta["title"]
                break

    title = title_from_meta or name_list
    msg = f"# {title}\n\n"
    if language == "pl":
        msg += f"Plik **{name_list}** został przesłany. Nie udało się wyodrębnić treści tekstowej — dokument może zawierać wyłącznie obrazy lub być zabezpieczony. Możesz zadać pytanie, a postaram się pomóc."
    else:
        msg += f"**{name_list}** has been uploaded. Text extraction was not possible — the document may contain only images or be protected. Feel free to ask a question and I'll do my best to help."
    return msg


# Keys to always exclude from the metadata block shown to the model
_META_EXCLUDE_KEYS = {
    "file_name",
    "file_created",
    "file_modified",
    "file_size_bytes",
    "exif",
    "web_detection",
    "identification",
    "producer",
    "creator",
}

# ── Token budget for the describe prompt ─────────────────────────────
# Organization TPM (tokens per minute) limit for gpt-5.4-mini: 200K.
# Context windows: gpt-5.4-mini ~1M, claude-3-5-haiku ~200K, gemma4 ~128K.
# We keep the content budget generous but respect TPM constraints.
# ~30K tokens ≈ 120K chars is safe for a single call.
_DESCRIBE_MAX_CONTENT_CHARS = 120_000
# When a document is large, we split the budget: 50% for raw text from start,
# 20% for 2-pass summaries of remaining content, 30% for page summaries.
_TEXT_BUDGET_RATIO = 0.50
_SUMMARY_PASS_BUDGET_RATIO = 0.20
# Threshold for triggering 2-pass summarization (chars of total extracted text)
_TWO_PASS_THRESHOLD = 200_000
# Threshold for triggering multi-part split+synthesize strategy.
# Documents above this size get split into N parts, each generating a
# detailed condensed summary, then synthesized into one welcome message.
# ~800K chars ≈ 200K tokens. Well above single-call capacity.
_SPLIT_THRESHOLD = 800_000
# Max chars of text to send per partial welcome message call.
# ~150K chars ≈ 37K tokens. Each part produces a detailed "condensed summary"
# of its section (~10 pages worth of detail).
_SPLIT_PART_MAX_CHARS = 150_000
# Delay between sequential LLM calls (seconds) to spread out TPM usage.
# Each call uses ~40K tokens; serial execution avoids bursting past 200K TPM.
_SPLIT_INTER_CALL_DELAY = 2.0
# How many chars of raw book text to include in the synthesis prompt.
# ~200 pages ≈ 400K chars. This gives the synthesis LLM direct access to the
# beginning of the book alongside the condensed summaries.
_SYNTHESIS_RAW_TEXT_CHARS = 400_000
# Whole-book path: if the book fits inside this estimated token budget,
# send the full raw text to the welcome-message prompt instead of truncating.
_WHOLE_BOOK_MAX_ESTIMATED_TOKENS = 250_000
# Keep the extracted raw text in memory up to 500 MB as requested.
_WHOLE_BOOK_MEMORY_LIMIT_BYTES = 500 * 1024 * 1024
# Large-book compaction path packs adjacent chapters/page ranges into 4-8 LLM calls.
_BOOK_COMPACTION_MIN_GROUPS = 4
_BOOK_COMPACTION_MAX_GROUPS = 8
_BOOK_COMPACTION_TOKENS_PER_GROUP = 60_000
_RAW_ENDING_CHARS = 120_000
# Max retries for 429 rate-limit errors
_LLM_MAX_RETRIES = 3
_LLM_RETRY_BASE_DELAY = 2.0

# ── Suggested questions rules (appended to describe prompts) ─────────
_QUESTIONS_RULES_PL = """

== SUGEROWANE PYTANIA ==
Po wiadomości powitalnej, wypisz DOKŁADNIE tę linię separatora:
---SUGGESTED_QUESTIONS---
Następnie wypisz prawidłowy JSON (bez markdown, bez ```json):
{{"questions": ["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8", "q9", "q10"]}}

Zasady:
- Wygeneruj do 10 sugerowanych promptów (celuj w 10, jeśli kontekst pozwala)
- Pierwsze 3 to naturalne pytania o treść dokumentu (krótkie, konkretne, klikalne) — BEZ emoji
- Jeśli dokument jest autorstwa lub dotyczy znanej osoby, JEDNO z pierwszych 3 pytań MUSI brzmieć "Kim był [Imię Nazwisko]?" (jeśli nie żyje) lub "Kim jest [Imię Nazwisko]?" (jeśli żyje)
- Kolejne (do 7) to kreatywne prompty-akcje z emoji na końcu (np. "Stwórz quiz z kluczowych faktów 🧠", "Napisz inspirowany wiersz 📜")
- Każdy prompt max 10 słów, bez numeracji, bez wyjaśnień
- WSZYSTKIE prompty muszą być w 100% w języku treści dokumentu

Obowiązkowe akcje dla typów treści:
- POWIEŚĆ/BELETRYSTYKA → "Napisz inspirowany rozdział w stylu [Imię Nazwisko autora] ✏️"
- POEZJA/FILOZOFIA/CYTATY → "Napisz inspirowany wiersz w stylu [Imię Nazwisko autora] 📜"
- PORADNIK/SAMOROZWÓJ → losowo jedno z: "Napisz 10 nowych wskazówek inspirowanych [autor] 💡", "Stwórz 7 ćwiczeń inspirowanych [autor] 🏋️", "Wygeneruj 12 pytań refleksyjnych inspirowanych [autor] 🤔", "Napisz 5 scenariuszy z życia inspirowanych [autor] 🎭", "Stwórz 14-dniowy plan działania inspirowany [autor] 📅"
- WYNIKI BADAŃ LAB → "Postaw diagnozę na podstawie wyników 🔬"
- Inne typy → dobierz kreatywne akcje losowo z: quiz 🧠, checklista ✅, diagram mermaid 🖼️, tabela porównawcza 📊, podsumowanie 📝, wyjaśnij jak dla dziecka 👶, fiszki 🃏, oś czasu 📅, mapa myśli 🧩, za i przeciw ⚖️, szkic emaila 📧, notatki do nauki 📓, FAQ ❓, debata 💬, słownik pojęć 📖, plan działania 🚩, post na social media 📱, streszczenie wykonawcze 🎯, dialog 🎬, infografika 📊, piosenka 🎵, prezentacja 📽️, bajka 🧚, wygeneruj obraz 🎨
- Nie zawsze wybieraj quiz — bądź kreatywny i zróżnicowany"""

_QUESTIONS_RULES_EN = """

== SUGGESTED QUESTIONS ==
After the welcome message, output EXACTLY this separator line:
---SUGGESTED_QUESTIONS---
Then output valid JSON (no markdown, no ```json):
{{"questions": ["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8", "q9", "q10"]}}

Rules:
- Generate up to 10 suggested prompts (target 10 when context allows)
- First 3 are natural questions about the document content (short, specific, clickable) — NO emoji
- If the document is by or about a well-known person, ONE of the first 3 MUST be "Who was [Full Name]?" (if deceased) or "Who is [Full Name]?" (if alive)
- The next prompts (up to 7) are creative action-prompts ending with emoji (e.g., "Create a quiz from key facts 🧠", "Write an inspired poem 📜")
- Each prompt max 10 words, no numbering, no explanations
- ALL prompts MUST be written 100% in the language of the document content

Mandatory actions for content types:
- NOVEL/FICTION → "Write inspired chapter like [Author Full Name] ✏️"
- POETRY/PHILOSOPHY/QUOTES → "Write inspired poem like [Author Full Name] 📜"
- SELF-HELP/GUIDE → randomly pick one of: "Write 10 new tips inspired by [author] 💡", "Create 7 exercises inspired by [author] 🏋️", "Generate 12 reflection questions inspired by [author] 🤔", "Draft 5 real-life scenarios inspired by [author] 🎭", "Build a 14-day action plan inspired by [author] 📅"
- LAB TEST RESULTS → "Make a diagnosis based on results 🔬"
- Other types → pick creative actions randomly from: quiz 🧠, checklist ✅, mermaid diagram 🖼️, comparison table 📊, summary 📝, explain like I'm 5 👶, flashcards 🃏, timeline 📅, mind map 🧩, pros & cons ⚖️, email draft 📧, study notes 📓, FAQ ❓, debate 💬, glossary 📖, action plan 🚩, social media post 📱, executive summary 🎯, dialogue 🎬, infographic 📊, song 🎵, presentation 📽️, fairy tale 🧚, generate image 🎨
- Do NOT always pick quiz — be creative and varied"""


def _parse_describe_response(response: str) -> tuple[str, list[str]]:
    """Split a combined describe response into welcome message and questions."""
    if _QUESTIONS_SEPARATOR in response:
        parts = response.split(_QUESTIONS_SEPARATOR, 1)
        welcome = parts[0].strip()
        json_part = parts[1].strip()
        try:
            parsed = json.loads(json_part)
            questions = parsed.get("questions", [])
            if isinstance(questions, list) and len(questions) >= 3:
                return welcome, [str(q) for q in questions[:10]]
        except (json.JSONDecodeError, AttributeError):
            logger.warning("Failed to parse suggested questions JSON from describe response")
        return welcome, []
    return response.strip(), []


def _estimate_total_text_len(extracted: list[dict]) -> int:
    """Return the total character count across all extracted documents."""
    return sum(len(doc.get("text") or "") for doc in extracted)


def _estimate_word_count(text: str) -> int:
    """Count words quickly without a heavyweight tokenizer."""
    if not text.strip():
        return 0
    return len(re.findall(r"\S+", text))


def _estimate_token_count(text: str, word_count: int | None = None) -> int:
    """Estimate tokens conservatively from chars and words."""
    words = word_count if word_count is not None else _estimate_word_count(text)
    return max(len(text) // 4, int(words * 1.35))


def _extract_pages(text: str) -> list[tuple[int, str]]:
    """Split extracted PDF text into page-numbered sections."""
    if not text.strip():
        return []

    matches = list(_PAGE_HEADER_RE.finditer(text))
    if not matches:
        return [(1, text.strip())]

    pages: list[tuple[int, str]] = []
    for index, match in enumerate(matches):
        page_number = int(match.group(1))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        pages.append((page_number, text[start:end].strip()))
    return pages


def _resolve_page_count(
    extracted: list[dict],
    file_metadata: dict[str, dict] | None,
    page_summaries: list[dict] | None,
) -> int:
    """Resolve page count from metadata first, then from extracted page markers."""
    if file_metadata:
        for meta in file_metadata.values():
            page_count = meta.get("page_count") if isinstance(meta, dict) else None
            if isinstance(page_count, int) and page_count > 0:
                return page_count

    if page_summaries:
        pages = [ps.get("page") for ps in page_summaries if isinstance(ps.get("page"), int)]
        if pages:
            return max(pages)

    detected_pages: list[int] = []
    for doc in extracted:
        detected_pages.extend(page_number for page_number, _text in _extract_pages(doc.get("text") or ""))
    return max(detected_pages) if detected_pages else 0


def _build_page_summary_block(page_summaries: list[dict]) -> str:
    """Build a compact summary-per-page block from page summaries."""
    lines: list[str] = []
    for ps in page_summaries:
        page = ps.get("page", "?")
        fname = clean_file_name(ps.get("file_name", ""))
        summary = ps.get("summary", "").strip()
        if summary:
            prefix = f"[{fname} p.{page}]" if fname else f"[p.{page}]"
            lines.append(f"{prefix} {summary}")
    return "\n".join(lines)


def _invoke_with_retry(
    chain, params: dict, label: str = "LLM call", *, conversation_id: str | None = None,
) -> str:
    """Invoke a LangChain chain with retry on 429 rate-limit errors.

    Wraps each attempt with OTel tracing, metrics, and prompt history logging.
    """
    model = "unknown"
    try:
        llm = get_llm()
        model = getattr(llm, "model", None) or getattr(llm, "model_name", None) or "unknown"
    except Exception:
        pass

    for attempt in range(_LLM_MAX_RETRIES + 1):
        try:
            response_text, _usage = traced_llm_call(
                chain=chain,
                params=params,
                operation=f"describe.{label}",
                model=model,
                conversation_id=conversation_id,
                rendered_prompt=str(params)[:500_000],
            )
            return response_text
        except Exception as e:
            error_str = str(e)
            is_rate_limit = "429" in error_str or "rate_limit" in error_str.lower()
            if is_rate_limit and attempt < _LLM_MAX_RETRIES:
                delay = _LLM_RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    f"⚠️ Rate limit hit for {label} (attempt {attempt + 1}), "
                    f"retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
                continue
            raise


def _summarize_text_chunk(text: str, chunk_label: str, language: str) -> str:
    """Summarize a large chunk of text into a dense condensed summary.

    Used in the 2-pass strategy for very large documents: each half of the
    document is summarized separately, then combined with raw text from the
    beginning for the final welcome message prompt.
    """
    if not text.strip():
        return ""

    if language == "pl":
        system_msg = (
            "Jesteś ekspertem od streszczania dokumentów. Otrzymasz fragment dużego dokumentu. "
            "Stwórz gęste, szczegółowe streszczenie zachowując WSZYSTKIE kluczowe fakty, nazwiska, daty, kwoty, "
            "wnioski i argumenty. Dla każdej strony/sekcji napisz 2-3 zdania wyciągając najważniejsze informacje. "
            "Zachowaj oryginalną strukturę i kolejność. NIE pomijaj ważnych szczegółów. "
            "Pisz zwięźle ale kompletnie — to streszczenie będzie jedynym źródłem informacji o tej części dokumentu."
        )
    else:
        system_msg = (
            "You are an expert document summarizer. You will receive a section of a large document. "
            "Create a dense, detailed summary preserving ALL key facts, names, dates, amounts, "
            "conclusions, and arguments. For each page/section, write 2-3 sentences extracting the crucial information. "
            "Maintain the original structure and order. Do NOT skip important details. "
            "Write concisely but completely — this summary will be the only source of information about this part of the document."
        )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_msg),
            ("human", f"Document section ({chunk_label}):\n\n{{text}}"),
        ]
    )

    llm = get_llm()
    chain = prompt | llm | StrOutputParser()
    result = _invoke_with_retry(chain, {"text": text}, label=f"2-pass summary ({chunk_label})")
    logger.info(f"📝 2-pass summary for {chunk_label}: {len(text)} chars → {len(result)} chars")
    return result.strip()


def _split_text_into_parts(full_text: str, max_chars_per_part: int) -> list[str]:
    """Split text into roughly equal parts, each ≤ max_chars_per_part.

    Tries to split at page boundaries (# Page N headers) for cleaner breaks.
    """
    if len(full_text) <= max_chars_per_part:
        return [full_text]

    n_parts = math.ceil(len(full_text) / max_chars_per_part)
    target_size = len(full_text) // n_parts
    parts: list[str] = []
    start = 0

    for i in range(n_parts):
        if i == n_parts - 1:
            parts.append(full_text[start:])
            break

        end = start + target_size
        # Try to find a page boundary near the target split point
        search_start = max(start, end - 2000)
        search_end = min(len(full_text), end + 2000)
        search_region = full_text[search_start:search_end]

        # Look for "# Page N" markers to split cleanly
        best_split = -1
        import re

        for m in re.finditer(r"\n# Page \d+", search_region):
            candidate = search_start + m.start()
            if candidate > start:
                best_split = candidate

        if best_split > start:
            parts.append(full_text[start:best_split])
            start = best_split
        else:
            # Fall back to splitting at a paragraph boundary
            newline_pos = full_text.rfind("\n\n", start + target_size - 1000, end + 1000)
            if newline_pos > start:
                parts.append(full_text[start:newline_pos])
                start = newline_pos
            else:
                parts.append(full_text[start:end])
                start = end

    return [p for p in parts if p.strip()]


def _build_book_sections(
    *,
    pages: list[tuple[int, str]],
    chapters: list[dict] | None,
    total_pages: int,
    estimated_tokens: int,
) -> list[dict]:
    """Build chapter-based or fallback page-range sections for large books."""
    if not pages:
        return []

    last_page = max(page_number for page_number, _text in pages)
    normalized_chapters: list[dict] = []

    if chapters:
        for index, chapter in enumerate(chapters, start=1):
            start_page = int(chapter.get("start_page") or chapter.get("pageFrom") or 0)
            end_page = int(chapter.get("end_page") or chapter.get("pageTo") or 0)
            if start_page <= 0 or end_page < start_page:
                continue
            name = (
                chapter.get("chapter_name")
                or chapter.get("name")
                or chapter.get("title")
                or f"Chapter {index}"
            )
            normalized_chapters.append(
                {
                    "name": str(name),
                    "start_page": start_page,
                    "end_page": min(end_page, last_page),
                }
            )

    if normalized_chapters:
        return normalized_chapters

    target_groups = max(
        _BOOK_COMPACTION_MIN_GROUPS,
        min(_BOOK_COMPACTION_MAX_GROUPS, math.ceil(estimated_tokens / _BOOK_COMPACTION_TOKENS_PER_GROUP)),
    )
    target_groups = max(1, min(target_groups, len(pages)))
    pages_per_group = max(1, math.ceil(max(total_pages, last_page) / target_groups))

    sections: list[dict] = []
    current_start = 1
    while current_start <= last_page:
        current_end = min(last_page, current_start + pages_per_group - 1)
        sections.append(
            {
                "name": f"Pages {current_start}-{current_end}",
                "start_page": current_start,
                "end_page": current_end,
            }
        )
        current_start = current_end + 1

    return sections


def _pack_book_sections(section_ranges: list[dict], total_pages: int, estimated_tokens: int) -> list[dict]:
    """Pack adjacent sections into 4-8 larger LLM requests."""
    if not section_ranges:
        return []

    target_groups = max(
        _BOOK_COMPACTION_MIN_GROUPS,
        min(_BOOK_COMPACTION_MAX_GROUPS, math.ceil(estimated_tokens / _BOOK_COMPACTION_TOKENS_PER_GROUP)),
    )
    target_groups = max(1, min(target_groups, len(section_ranges)))
    target_pages = max(1, math.ceil(max(total_pages, 1) / target_groups))

    packed: list[dict] = []
    current_sections: list[dict] = []
    current_pages = 0

    for section in section_ranges:
        section_pages = max(1, section["end_page"] - section["start_page"] + 1)
        should_flush = (
            current_sections
            and current_pages + section_pages > target_pages
            and len(packed) < target_groups - 1
        )
        if should_flush:
            packed.append(
                {
                    "sections": current_sections,
                    "start_page": current_sections[0]["start_page"],
                    "end_page": current_sections[-1]["end_page"],
                }
            )
            current_sections = []
            current_pages = 0

        current_sections.append(section)
        current_pages += section_pages

    if current_sections:
        packed.append(
            {
                "sections": current_sections,
                "start_page": current_sections[0]["start_page"],
                "end_page": current_sections[-1]["end_page"],
            }
        )

    return packed


def _build_group_text(pages: list[tuple[int, str]], group: dict) -> str:
    """Build text for one packed chapter/page-range group."""
    page_map = {page_number: text for page_number, text in pages}
    blocks: list[str] = []

    for section in group["sections"]:
        section_pages: list[str] = []
        for page_number in range(section["start_page"], section["end_page"] + 1):
            page_text = page_map.get(page_number, "")
            if page_text.strip():
                section_pages.append(f"# Page {page_number}\n\n{page_text}")
        if section_pages:
            blocks.append(
                f"===SECTION===\n"
                f"name: {section['name']}\n"
                f"pages: {section['start_page']}-{section['end_page']}\n\n"
                + "\n\n".join(section_pages)
            )

    return "\n\n-----\n\n".join(blocks)


def _generate_partial_welcome(
    part_text: str,
    part_index: int,
    total_parts: int,
    file_list: str,
    language: str,
    metadata_section: str,
) -> str:
    """Generate a detailed condensed summary for one part of a large document.

    Unlike a short welcome message, this produces a rich, dense summary
    (equivalent to ~10 pages of detail) that captures all key facts, characters,
    events, and concepts. These detailed summaries are later synthesized into
    the final welcome message.
    """
    if language == "pl":
        system_msg = (
            "Tworzysz SZCZEGÓŁOWE STRESZCZENIE CZĘŚCI dużego dokumentu. "
            f"To jest część {part_index + 1} z {total_parts}.\n\n"
            "Twoim zadaniem jest wyciągnąć WSZYSTKIE istotne informacje z tego fragmentu "
            "i stworzyć gęste, szczegółowe streszczenie — jakby skrócić 500 stron do 10.\n\n"
            "Twoja odpowiedź MUSI zawierać:\n"
            "- **Tytuł i autor** (tylko jeśli to część 1 i możesz je rozpoznać)\n"
            "- **WSZYSTKIE imiona postaci/osób** z pogrubionymi nazwami\n"
            "- **Kluczowe wydarzenia** w kolejności chronologicznej\n"
            "- **Miejsca, daty, kwoty, statystyki** — każda konkretna liczba\n"
            "- **Główne tematy i argumenty** z tej części\n"
            "- **Relacje między postaciami/elementami**\n"
            "- **Zwroty akcji, kluczowe cytaty, wnioski**\n\n"
            "Pisz gęsto i szczegółowo — to streszczenie będzie jedynym źródłem "
            "informacji o tej części dokumentu. Każde zdanie musi nieść konkretne fakty.\n"
            "NIE pisz ogólników. NIE pytaj użytkownika. NIE używaj [source:N].\n"
            "Odpowiadaj po polsku."
        )
    else:
        system_msg = (
            "You are creating a DETAILED CONDENSED SUMMARY of ONE PART of a large document. "
            f"This is part {part_index + 1} of {total_parts}.\n\n"
            "Your job is to extract ALL important information from this section and create "
            "a dense, detailed summary — as if condensing 500 pages into 10.\n\n"
            "Your response MUST include:\n"
            "- **Title and author** (only if this is part 1 and you can identify them)\n"
            "- **ALL character/person names** with bold formatting\n"
            "- **Key events** in chronological order\n"
            "- **Places, dates, amounts, statistics** — every specific number\n"
            "- **Main themes and arguments** from this section\n"
            "- **Relationships between characters/elements**\n"
            "- **Plot twists, key quotes, conclusions**\n\n"
            "Write densely and in detail — this summary will be the ONLY source of information "
            "about this part of the document. Every sentence must carry concrete facts.\n"
            "Do NOT write generalities. Do NOT ask the user anything. Do NOT use [source:N].\n"
            "Reply in the same language as the content."
        )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_msg),
            (
                "human",
                "Files: {file_list}\n\nContent (part {part_num}/{total}):\n{content}{metadata_section}",
            ),
        ]
    )

    llm = get_llm()
    chain = prompt | llm | StrOutputParser()
    result = _invoke_with_retry(
        chain,
        {
            "file_list": file_list,
            "part_num": str(part_index + 1),
            "total": str(total_parts),
            "content": part_text,
            "metadata_section": metadata_section,
        },
        label=f"partial summary {part_index + 1}/{total_parts}",
    )
    logger.info(
        f"📝 Detailed summary {part_index + 1}/{total_parts}: "
        f"{len(part_text)} chars text → {len(result)} chars summary"
    )
    return result.strip()


def _generate_compacted_book_group(
    group_text: str,
    group_index: int,
    total_groups: int,
    file_list: str,
    language: str,
    metadata_section: str,
) -> str:
    """Compact one packed set of chapters/page-ranges into structured summaries."""
    if language == "pl":
        system_msg = (
            "Otrzymasz kilka kolejnych rozdziałów lub zakresów stron tej samej książki. "
            f"To pakiet {group_index + 1} z {total_groups}.\n\n"
            "Dla KAŻDEJ sekcji zachowaj osobny blok w dokładnie takim formacie:\n"
            "===SECTION===\n"
            "name: <nazwa sekcji>\n"
            "pages: <zakres stron>\n"
            "summary:\n"
            "- ...\n"
            "- ...\n\n"
            "Skróć każdą sekcję do około 10-15% objętości, ale zachowaj fabułę, bohaterów, "
            "fakty, liczby, miejsca, relacje, zwroty akcji i ważne szczegóły. "
            "Nie mieszaj sekcji ze sobą. Nie pomijaj zakończeń scen i ważnych przejść. "
            "Pisz po polsku."
        )
    else:
        system_msg = (
            "You will receive several consecutive chapters or page ranges from the same book. "
            f"This is pack {group_index + 1} of {total_groups}.\n\n"
            "For EACH section, keep a separate block in exactly this format:\n"
            "===SECTION===\n"
            "name: <section name>\n"
            "pages: <page range>\n"
            "summary:\n"
            "- ...\n"
            "- ...\n\n"
            "Compress each section to about 10-15% of its volume while preserving plot, people, "
            "facts, numbers, places, relationships, twists, and key details. "
            "Do not merge sections together. Do not skip endings of scenes or important transitions. "
            "Reply in the same language as the content."
        )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_msg),
            (
                "human",
                "Files: {file_list}\n\nSections to compact:\n{content}{metadata_section}",
            ),
        ]
    )

    llm = get_llm()
    chain = prompt | llm | StrOutputParser()
    result = _invoke_with_retry(
        chain,
        {
            "file_list": file_list,
            "content": group_text,
            "metadata_section": metadata_section if group_index == 0 else "",
        },
        label=f"book compact {group_index + 1}/{total_groups}",
    )
    logger.info(
        f"📝 Book compact {group_index + 1}/{total_groups}: "
        f"{len(group_text)} chars → {len(result)} chars"
    )
    return result.strip()


def _synthesize_welcome_messages(
    partial_messages: list[str],
    file_list: str,
    language: str,
    metadata_section: str,
    raw_beginning: str = "",
    raw_ending: str = "",
) -> tuple[str, list[str]]:
    """Synthesize N detailed condensed summaries into one final welcome message.

    Returns (welcome_message, suggested_questions).

    When raw_beginning is provided, the LLM also receives the first ~200 pages
    of raw book text alongside the condensed summaries — giving it direct access
    to the author's voice, style, and opening content for a smarter result.
    """
    if len(partial_messages) == 1 and not raw_beginning:
        return partial_messages[0], []

    combined_partials = "\n\n---\n\n".join(
        f"[Detailed summary of section {i + 1} of {len(partial_messages)}]\n{msg}"
        for i, msg in enumerate(partial_messages)
    )

    raw_parts: list[str] = []
    if raw_beginning:
        raw_parts.append(
            f"Raw text from the beginning of the document "
            f"(first ~{len(raw_beginning) // 1000}K chars):\n{raw_beginning}"
        )
    if raw_ending:
        raw_parts.append(
            f"Raw text from the ending of the document "
            f"(last ~{len(raw_ending) // 1000}K chars):\n{raw_ending}"
        )

    raw_block = ""
    if raw_parts:
        raw_block = "\n\n=====\n" + "\n\n-----\n\n".join(raw_parts) + "\n====="

    if language == "pl":
        system_msg = (
            "Otrzymujesz SZCZEGÓŁOWE STRESZCZENIA różnych CZĘŚCI tego samego dużego dokumentu "
            "(książki/PDF). Każde streszczenie obejmuje inną sekcję i zawiera gęste, "
            "szczegółowe informacje o treści.\n\n"
            "Dodatkowo możesz otrzymać surowy tekst z początku dokumentu — wykorzystaj go "
            "aby uchwycić styl autora, ton i kontekst otwierający.\n\n"
            "Twoim zadaniem jest POŁĄCZYĆ te streszczenia w jedną, spójną wiadomość powitalną.\n\n"
            "Twoja odpowiedź MUSI składać się z trzech części:\n"
            "1. **Tytuł**: # Tytuł dokumentu - Autor\n"
            "2. **Opis**: 2-3 zdania podsumowujące CAŁY dokument. Zachowaj najważniejsze "
            "fakty, nazwiska, miejsca z WSZYSTKICH części. Używaj **pogrubienia**.\n"
            "3. **Ekspercki wgląd**: 1-2 zdania wartościowej analizy.\n\n"
            "WAŻNE: Musisz zsyntetyzować informacje z WSZYSTKICH streszczeń, nie tylko pierwszego. "
            "Celuj w 150-250 słów łącznie (1-4 akapitów, najczęściej 3, czasem 2, rzadko 4). NIE pytaj użytkownika. NIE używaj [source:N]. "
            "Używaj emoji profesjonalnie (📖, ⚔️, 🗺️ itp.).\n"
            "Odpowiadaj po polsku."
        ) + _QUESTIONS_RULES_PL
    else:
        system_msg = (
            "You are receiving DETAILED CONDENSED SUMMARIES of different PARTS of the same "
            "large document (book/PDF). Each summary covers a different section and contains "
            "dense, detailed information about the content.\n\n"
            "You may also receive raw text from the beginning of the document — use it "
            "to capture the author's voice, tone, and opening context.\n\n"
            "Your job is to MERGE these summaries into one cohesive welcome message.\n\n"
            "Your response MUST have three parts:\n"
            "1. **Title**: # Document Title - Author Name\n"
            "2. **Description**: 2-3 sentences summarizing the ENTIRE document. Preserve the key "
            "facts, names, places from ALL parts. Use **bold** for key terms.\n"
            "3. **Expert insight**: 1-2 sentences of valuable analysis.\n\n"
            "IMPORTANT: Synthesize information from ALL summaries, not just the first. "
            "Aim for 150-250 words total (1-4 paragraphs, usually 3, sometimes 2, rarely 4). Do NOT ask the user anything. Do NOT use [source:N]. "
            "Use emoji professionally (📖, ⚔️, 🗺️ etc.).\n"
            "Reply in the same language as the content."
        ) + _QUESTIONS_RULES_EN

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_msg),
            (
                "human",
                "Files: {file_list}\n\nDetailed summaries to synthesize:\n\n{partials}{raw_block}{metadata_section}",
            ),
        ]
    )

    llm = get_llm()
    chain = prompt | llm | StrOutputParser()
    result = _invoke_with_retry(
        chain,
        {
            "file_list": file_list,
            "partials": combined_partials,
            "raw_block": raw_block,
            "metadata_section": metadata_section,
        },
        label="synthesis",
    )
    logger.info(
        f"📝 Synthesized {len(partial_messages)} summaries "
        f"(+ {len(raw_beginning)} chars raw start, {len(raw_ending)} chars raw end) → {len(result)} chars final"
    )
    return _parse_describe_response(result)


def describe_documents(
    extracted: list[dict],
    images: list[dict],
    language: str | None = None,
    file_metadata: dict[str, dict] | None = None,
    page_summaries: list[dict] | None = None,
    file_names: list[str] | None = None,
    file_types: dict[str, str] | None = None,
    chapters: list[dict] | None = None,
) -> DescribeResult:
    """Generate a welcome message with a # Title, description, and expert insight,
    plus up to 10 suggested questions — all from a single LLM call.

    Returns a DescribeResult dict with 'welcome_message' and 'suggested_questions'.

    Uses the beginning of extracted text (no embeddings/RAG) so the response
    is as quick as possible. When a whole book fits inside the budget, the full
    raw text is sent in one call. Larger books are compacted chapter-by-chapter
    or page-range-by-page-range, then synthesized with raw beginning/end text.
    """
    total_chars = _estimate_total_text_len(extracted)

    # ── Pre-compute metadata block and language (needed by all strategies) ──
    metadata_block = ""
    if file_metadata:
        meta_parts: list[str] = []
        for fname, meta in file_metadata.items():
            try:
                useful = {k: v for k, v in meta.items() if k not in _META_EXCLUDE_KEYS and v}
                if useful:
                    meta_parts.append(
                        f"[{fname}]\n{json.dumps(useful, ensure_ascii=False, default=str)}"
                    )
            except Exception as e:
                logger.warning(f"⚠️ Failed to format metadata for {fname}: {e}")
        if meta_parts:
            metadata_block = "\n\n".join(meta_parts)

    metadata_section = ""
    if metadata_block:
        metadata_section = (
            f"\n\n=====\nFile metadata (from EXIF / PDF info):\n{metadata_block}\n====="
        )

    file_names = [clean_file_name(doc.get("file_name", "")) for doc in extracted]
    file_names += [clean_file_name(img.get("file_name", "")) for img in images]
    file_list = ", ".join(dict.fromkeys(fn for fn in file_names if fn))
    all_text = "\n\n---\n\n".join(
        (doc.get("text") or "") for doc in extracted if (doc.get("text") or "").strip()
    )
    word_count = _estimate_word_count(all_text)
    estimated_tokens = _estimate_token_count(all_text, word_count)
    total_pages = _resolve_page_count(extracted, file_metadata, page_summaries)

    if language is None:
        sample_text = ""
        for doc in extracted:
            sample_text = (doc.get("text") or "")[:2000]
            if sample_text:
                break
        language = detect_language(sample_text) if sample_text else "en"

    if all_text and len(all_text.encode("utf-8")) <= _WHOLE_BOOK_MEMORY_LIMIT_BYTES:
        logger.info(
            f"📚 Welcome input stats: pages={total_pages or '?'} words={word_count} "
            f"estimated_tokens={estimated_tokens} chars={len(all_text)}"
        )

    # ── Strategy 1: Whole-book prompt when it fits ──────────────────
    if all_text and estimated_tokens <= _WHOLE_BOOK_MAX_ESTIMATED_TOKENS:
        logger.info(
            f"📚 Whole-book welcome strategy: {total_pages or '?'} pages, {word_count} words, "
            f"~{estimated_tokens} tokens"
        )

    # ── Strategy 2: Chapter/page-range compaction for large books ───
    elif all_text and len(extracted) == 1 and total_pages >= 1:
        logger.info(
            f"📚 Large-book welcome strategy: {total_pages} pages, {word_count} words, "
            f"~{estimated_tokens} tokens"
        )
        pages = _extract_pages(all_text)
        section_ranges = _build_book_sections(
            pages=pages,
            chapters=chapters,
            total_pages=total_pages,
            estimated_tokens=estimated_tokens,
        )
        groups = _pack_book_sections(section_ranges, total_pages, estimated_tokens)

        compacted: list[tuple[int, str]] = []
        with ThreadPoolExecutor(max_workers=min(len(groups), _BOOK_COMPACTION_MAX_GROUPS)) as pool:
            futures = {}
            for index, group in enumerate(groups):
                group_text = _build_group_text(pages, group)
                if not group_text.strip():
                    continue
                futures[pool.submit(
                    _generate_compacted_book_group,
                    group_text,
                    index,
                    len(groups),
                    file_list,
                    language,
                    metadata_section,
                )] = index

            for future in futures:
                index = futures[future]
                try:
                    compacted.append((index, future.result()))
                except Exception as e:
                    logger.warning(f"⚠️ Book compact group {index + 1} failed: {e}")

        compacted.sort(key=lambda item: item[0])
        compacted_messages = [message for _, message in compacted if message.strip()]
        if compacted_messages:
            synthesis_msg, synthesis_qs = _synthesize_welcome_messages(
                compacted_messages,
                file_list,
                language,
                metadata_section,
                raw_beginning=all_text[:_SYNTHESIS_RAW_TEXT_CHARS],
                raw_ending=all_text[-_RAW_ENDING_CHARS:] if len(all_text) > _RAW_ENDING_CHARS else "",
            )
            return DescribeResult(welcome_message=synthesis_msg, suggested_questions=synthesis_qs)

        logger.warning("⚠️ Book compaction produced no summaries, falling back to split/truncated strategy")

    # ── Strategy 3: Split+Synthesize for very large documents ────────
    # For documents > _SPLIT_THRESHOLD chars (~800K), split the full text
    # into N parts, generate a detailed condensed summary for each (sequentially
    # to respect TPM limits), then synthesize all summaries + raw beginning
    # into one final welcome message.
    if total_chars > _SPLIT_THRESHOLD:
        logger.info(
            f"📝 Very large document ({total_chars} chars) → using split+synthesize strategy"
        )
        parts = _split_text_into_parts(all_text, _SPLIT_PART_MAX_CHARS)
        logger.info(f"📝 Split into {len(parts)} parts ({[len(p) for p in parts[:5]]}...)")

        # Generate detailed condensed summaries sequentially to stay under TPM
        partial_messages: list[tuple[int, str]] = []
        for i, part in enumerate(parts):
            try:
                msg = _generate_partial_welcome(
                    part,
                    i,
                    len(parts),
                    file_list,
                    language,
                    metadata_section if i == 0 else "",
                )
                partial_messages.append((i, msg))
            except Exception as e:
                logger.warning(f"⚠️ Detailed summary {i + 1} failed: {e}")

            # Delay between calls to spread TPM usage
            if i < len(parts) - 1:
                time.sleep(_SPLIT_INTER_CALL_DELAY)

        # Sort by part index to maintain order
        partial_messages.sort(key=lambda x: x[0])
        messages = [msg for _, msg in partial_messages]

        if not messages:
            return DescribeResult(
                welcome_message=_fallback_from_metadata(extracted, images, file_metadata, language),
                suggested_questions=[],
            )

        if len(messages) == 1:
            return DescribeResult(welcome_message=messages[0], suggested_questions=[])

        # Extract raw beginning text for the synthesis prompt.
        # This gives the synthesis LLM direct access to the author's voice
        # and opening content alongside the condensed summaries.
        raw_beginning = all_text[:_SYNTHESIS_RAW_TEXT_CHARS]

        # Synthesize all detailed summaries + raw beginning into one message
        synthesis_msg, synthesis_qs = _synthesize_welcome_messages(
            messages, file_list, language, metadata_section, raw_beginning=raw_beginning
        )
        return DescribeResult(welcome_message=synthesis_msg, suggested_questions=synthesis_qs)

    whole_book_mode = bool(all_text and estimated_tokens <= _WHOLE_BOOK_MAX_ESTIMATED_TOKENS)
    is_large = total_chars > _DESCRIBE_MAX_CONTENT_CHARS and page_summaries and not whole_book_mode

    # ── Build image snippets (always included, capped) ───────────────
    image_snippets: list[str] = []
    for img in images:
        desc = img.get("description", "")
        name = clean_file_name(img.get("file_name", "image"))
        page = img.get("page", "?")
        if desc:
            image_snippets.append(f"[Image from {name}, page {page}]\n{desc[:500]}")
    image_block = "\n\n---\n\n".join(image_snippets)

    if whole_book_mode:
        combined_parts = [all_text]
        if image_block:
            combined_parts.append(image_block)
        combined = "\n\n---\n\n".join(part for part in combined_parts if part.strip())
    elif is_large:
        # ── Large-document strategy ──────────────────────────────────
        # For very large documents (>200K chars), use 2-pass summarization:
        # 1. Raw text from the start of the document (50% budget)
        # 2. Summarize remaining content in 2 passes (20% budget)
        # 3. Per-page summaries for breadth (30% budget)
        image_chars = len(image_block)
        remaining = _DESCRIBE_MAX_CONTENT_CHARS - image_chars

        is_very_large = total_chars > _TWO_PASS_THRESHOLD

        if is_very_large:
            text_budget = int(remaining * _TEXT_BUDGET_RATIO)
            summary_pass_budget = int(remaining * _SUMMARY_PASS_BUDGET_RATIO)
            summary_budget = remaining - text_budget - summary_pass_budget
        else:
            text_budget = int(remaining * 0.7)
            summary_pass_budget = 0
            summary_budget = remaining - text_budget

        # Raw text from each document start (distribute budget evenly)
        per_doc = max(text_budget // max(len(extracted), 1), 500)
        text_snippets: list[str] = []
        for doc in extracted:
            name = clean_file_name(doc.get("file_name", "unknown"))
            text = (doc.get("text") or "")[:per_doc]
            if text.strip():
                text_snippets.append(f"[File: {name}]\n{text}")

        # Page summaries block
        summary_text = _build_page_summary_block(page_summaries)[:summary_budget]

        # 2-pass summarization for very large documents
        two_pass_summary = ""
        if is_very_large and summary_pass_budget > 0:
            # Collect remaining text (after the raw text budget) from all docs
            remaining_texts: list[str] = []
            for doc in extracted:
                full_text = doc.get("text") or ""
                if len(full_text) > per_doc:
                    remaining_texts.append(full_text[per_doc:])

            if remaining_texts:
                all_remaining = "\n\n---\n\n".join(remaining_texts)
                midpoint = len(all_remaining) // 2

                # Cap each half to avoid sending too much to the summarizer
                max_half = 80_000
                first_half = all_remaining[:midpoint][-max_half:]
                second_half = all_remaining[midpoint:][:max_half]

                # Summarize each half
                summary_1 = _summarize_text_chunk(
                    first_half, "first half (middle pages)", language
                )
                summary_2 = _summarize_text_chunk(
                    second_half, "second half (final pages)", language
                )

                two_pass_summary = f"[Condensed summary of middle pages]\n{summary_1}\n\n[Condensed summary of final pages]\n{summary_2}"
                two_pass_summary = two_pass_summary[:summary_pass_budget]
                logger.info(f"📝 2-pass summaries combined: {len(two_pass_summary)} chars")

        parts: list[str] = []
        if text_snippets:
            parts.append("\n\n---\n\n".join(text_snippets))
        if two_pass_summary:
            parts.append(
                f"[Dense summaries of document content beyond the raw text above — "
                f"generated via 2-pass summarization of the remaining {total_chars - text_budget} chars]\n{two_pass_summary}"
            )
        if summary_text:
            parts.append(
                f"[Short summaries of all pages — the full text above was truncated "
                f"because the document is very large ({total_chars} chars)]\n{summary_text}"
            )
        if image_block:
            parts.append(image_block)

        combined = "\n\n---\n\n".join(parts)
        if not combined.strip():
            return DescribeResult(
                welcome_message=_fallback_from_metadata(extracted, images, file_metadata, language),
                suggested_questions=[],
            )
        logger.info(
            f"📝 Large-doc describe: {total_chars} chars total → "
            f"{len(combined)} chars context (text {text_budget}, 2-pass {len(two_pass_summary)}, summaries {len(summary_text)})"
        )
    else:
        # ── Small-document strategy (original) ───────────────────────
        snippets: list[str] = []
        per_doc = max(_DESCRIBE_MAX_CONTENT_CHARS // max(len(extracted), 1), 3000)
        for doc in extracted:
            name = clean_file_name(doc.get("file_name", "unknown"))
            text = (doc.get("text") or "")[:per_doc]
            if text.strip():
                snippets.append(f"[File: {name}]\n{text}")
        snippets.extend(image_snippets)

        if not snippets:
            # No text extracted — return a minimal fallback from metadata
            return DescribeResult(
                welcome_message=_fallback_from_metadata(extracted, images, file_metadata, language),
                suggested_questions=[],
            )

        combined = "\n\n---\n\n".join(snippets)[:_DESCRIBE_MAX_CONTENT_CHARS]

    if language == "pl":
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """Tworzysz wiadomość powitalną, którą zobaczy użytkownik zaraz po przesłaniu pliku.
Ta wiadomość będzie czytana przez zwykłego człowieka — powinna brzmieć naturalnie i pomocnie.

KLUCZOWA ZASADA: Wciel się w rolę eksperta z dziedziny, której dotyczy przesłany dokument. Rozpoznaj kontekst i przyjmij odpowiednią perspektywę:
- Wyniki badań laboratoryjnych / medyczne → lekarz / diagnostyk
- Faktury, rachunki, dokumenty podatkowe → księgowy / doradca finansowy
- Umowy, regulaminy, dokumenty prawne → prawnik
- CV, list motywacyjny → rekruter / HR
- Artykuły naukowe, raporty → badacz / analityk
- Zdjęcia, grafiki → fotograf / analityk obrazu
- Kod źródłowy, logi → programista / DevOps
- Dane tabelaryczne, CSV → analityk danych
- Inne → specjalista w danej tematyce
Pisz z perspektywy tego eksperta — nie jako AI, ale jako kompetentna osoba, która przejrzała dokument.

Twoja odpowiedź MUSI składać się z trzech części:

1. **Tytuł** (pierwsza linia): Krótkie podsumowanie przesłanego pliku — tytuł, a po myślniku autor jeśli znany (lub "Nieznany autor" gdy brak danych).
   Sformatuj jako nagłówek Markdown: # Tytuł dokumentu - Imię Nazwisko Autora
   Na przykład: # Przewodnik po bliznach - Amanda Keyes
   Jeśli autor nie jest znany z treści ani metadanych, napisz: # Tytuł dokumentu - Nieznany autor
   WAŻNE: Oczyść tytuł z artefaktów technicznych — usuń oznaczenia wersji, daty rewizji, słowa typu "FINAL", "DRAFT", "v2", "copy", numery rewizji (np. "170123"), myślniki i znaki na końcu. Użytkownik powinien zobaczyć czysty, czytelny tytuł, nie wewnętrzną nazwę pliku.

2. **Opis** (po tytule): 2-3 zdania opisujące zawartość pliku. Racjonalny, neutralny ton. Bądź konkretny i szczegółowy — wymień najważniejsze fakty, tematy, nazwiska, kwoty, daty znalezione w treści. Używaj **pogrubienia** dla kluczowych terminów.
   AUTOR W OPISIE: Jeśli znasz autora dokumentu, wspomnij o nim naturalnie w pierwszym zdaniu opisu — tak jakbyś opisywał książkę znajomemu. Na przykład: "Ten 611-stronicowy zbiór poezji **Rumiego** to klasyczne wydanie arabskie Mathnawi." albo "Stephen King w tym **350-stronicowym** thrillerze zabiera czytelnika w mroczną podróż po Nowej Anglii." NIE powtarzaj suchego zapisu z tytułu — wpleć autora w naturalny sposób w treść opisu.
   KLUCZOWE — ZACHOWAJ PRECYZYJNE SZCZEGÓŁY: Zawsze podawaj dokładne liczby, zakresy, nazwy substancji, składników, terminów i konkretne wartości z dokumentu. Na przykład: jeśli tekst mówi o "bliznach do 12 miesięcy (z zaleceniami do 2 lat)", napisz właśnie tak — nie upraszczaj do "blizny do roku". Jeśli wymienione są konkretne składniki jak "witamina C, białko, cynk i selen", wymień je wszystkie. Jeśli podane są zakresy czasowe jak "9–12 miesięcy dla ciała i około 1 rok dla twarzy", podaj te dokładne przedziały. Szczegółowe dane liczbowe i nazwy własne to najcenniejsza informacja w opisie.
   NAZWY PRODUKTÓW, MAREK I OSÓB: Gdy dokument wymienia konkretne marki, produkty lub znane osoby, UŻYWAJ ICH Z NAZWY — nie uogólniaj. Na przykład: pisz "krem RegimA Forte Scar Cream" zamiast "krem na blizny"; "minerały Jane Iredale" zamiast "makijaż mineralny". Dotyczy to leków (Accutane, Retin-A), narzędzi (Photoshop, Figma), firm (Tesla, Google), osób (Warren Buffett, Marie Curie), miejsc (Klinika Mayo, MIT), produktów (iPhone 16, Model Y) i wszystkiego co nosi nazwę własną w treści dokumentu.
   OBOWIĄZKOWE MIERZALNE FAKTY — oprócz powyższego, KONIECZNIE wymień jak najwięcej z poniższych (jeśli występują w treści):
   - Liczba stron/rozdziałów/części (np. "**266-stronicowy** kryminał w **12 rozdziałach**")
   - Wszystkie imiona i nazwiska głównych postaci/osób, pogrubione (np. **Joanna Chyłka**, **Kordian Oryński**)
   - Kluczowe daty, lata, okresy (np. "akcja rozgrywa się w **2019 roku**")
   - Miejsca i lokalizacje (np. "wydarzenia w **Warszawie** i pod **Augustowem**")
   - Kwoty, procenty, statystyki (np. "**3,5 mln zł** odszkodowania")
   - Nazwy organizacji, firm, instytucji
   - Wymiary, wagi, odległości, powierzchnie (np. "działka **1200 m²**", "trasa **42 km**")
   - Wyniki pomiarów, wartości laboratoryjne, zakresy referencyjne (np. "TSH **2,34 mIU/l** przy normie 0,27–4,20")
   - Numery identyfikacyjne: NIP, REGON, numery umów, sygnatura sprawy, ISBN
   - Terminy, deadliny, daty ważności (np. "termin płatności **14 dni**", "ważne do **2027-03-01**")
   - Rankingi, pozycje, oceny (np. "**4,8/5** gwiazdek", "**#3** na liście bestsellerów")
   - Liczba uczestników, respondentów, próbka badawcza (np. "badanie na **1200 pacjentach**")
   Im więcej konkretnych, mierzalnych faktów — tym lepszy opis. Każde zdanie powinno zawierać co najmniej jedną liczbę, nazwę własną lub mierzalny fakt. Użytkownik powinien z opisu dowiedzieć się KONKRETNYCH rzeczy, nie ogólników.
   Jeśli w metadanych pliku jest pole page_count, KONIECZNIE wspomnij ile stron liczy dokument (np. "Ten **14-stronicowy** przewodnik...").
   Jeśli przesłano zdjęcie z metadanymi EXIF, wspomnij najciekawsze szczegóły (aparat, data, lokalizacja).
   Jeśli na zdjęciu widać osobę lub ludzi, napisz o tym.

3. **Ekspercki wgląd** (po opisie): 1-2 zdania z wartościową analizą eksperta. To najważniejsza część — musisz dać użytkownikowi coś przydatnego, czego sam mógłby nie zauważyć.
   NIE zaczynaj od zwrotów typu: "Warto zwrócić uwagę...", "Co istotne...", "Należy podkreślić...", "Najważniejszy wniosek to..." — to brzmi sztucznie.
   Zamiast tego, przejdź płynnie do meritum, jakbyś rozmawiał ze znajomym. Na przykład:
   - "Poziom homocysteiny 7,04 µmol/l mieści się w normie, natomiast warto zestawić go z..."
   - "Kwota netto na fakturze nie uwzględnia..."
   - "W tym CV brakuje sekcji..."
   Dostosuj się do kontekstu:
   - Wyniki badań: wskaż wartości poza normą, możliwe przyczyny, sugerowane dalsze kroki (kolejne badania, wizyta u specjalisty).
   - Dokumenty finansowe: zwróć uwagę na terminy płatności, nieprawidłowości, możliwe optymalizacje.
   - Dokumenty prawne: wskaż kluczowe zapisy, ryzyka, terminy.
   - Artykuły/raporty: wskaż główną tezę, zaskakujący wniosek lub kontekst.
   - Zdjęcia: opisz co ciekawego widać, kontekst techniczny lub artystyczny.
   - Dane/tabele: wskaż trend, anomalię lub najważniejszą liczbę.

Jeśli podano metadane pliku (JSON poniżej oznaczony =====), KONIECZNIE wykorzystaj je — np. autora, datę utworzenia, tytuł, aparat itp.
NIGDY nie wspominaj o wewnętrznych technicznych metadanych — pomijaj informacje typu: nazwa generatora PDF (np. "Skia/PDF", "Google Docs Renderer", "Microsoft Word", "LibreOffice", "wkhtmltopdf"), wersja producenta, ID dokumentu, format zapisu. Te dane są bezwartościowe dla użytkownika i brzmią jak wyciek z systemu.

Pisz jak człowiek, który opisuje dokument innemu człowiekowi — nie jak automat generujący streszczenie.
Bądź zwięzły — to ma być szybka analiza, nie rozprawka. Celuj w około 150-250 słów łącznie (opis + wgląd), używając 1-4 akapitów (najczęściej 3, czasem 2, rzadko 4). Nie rozwlekaj — każde zdanie musi nieść konkretną wartość.
NIE pytaj użytkownika o nic. NIE używaj odnośników źródłowych jak [1] ani [source:1].
Od czasu do czasu użyj profesjonalnych emoji, żeby wiadomość była bardziej żywa i łatwa do przeskanowania (np. ✅, 👌, 📄, 📊, 🔬, ⚠️, 💡, 📸, 🏥, ⚖️, 📝, 🔍, 📈, 🗓️, 💰, "inne fajne, lekkie, nieofensywne emoji"). Nie przesadzaj — jedno-dwa na sekcję wystarczą. Nigdy nie używaj dziecinnych lub nieprofesjonalnych emoji (💩, 🤡, 😜 itp.).
Odpowiadaj po polsku.""" + _QUESTIONS_RULES_PL,
                ),
                ("human", "Przesłane pliki: {file_list}\n\nTreść:\n{content}{metadata_section}"),
            ]
        )
    else:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are writing a welcome message that a human user will see right after uploading a file.
This message will be read by a real person — it should sound natural, friendly, and helpful.

KEY RULE: Adopt the role of an expert from the field the uploaded document belongs to. Identify the context and take on the appropriate perspective:
- Lab results / medical documents → doctor / diagnostician
- Invoices, receipts, tax documents → accountant / financial advisor
- Contracts, regulations, legal docs → lawyer
- CV, cover letter → recruiter / HR specialist
- Scientific articles, reports → researcher / analyst
- Photos, graphics → photographer / image analyst
- Source code, logs → developer / DevOps engineer
- Tabular data, CSV → data analyst
- Other → specialist in the relevant field
Write from that expert's perspective — not as an AI, but as a competent person who has reviewed the document.

Your response MUST have three parts:

1. **Title** (first line): The document title followed by a dash and the author name (or "Unknown author" if not available).
   Format as a Markdown heading: # Document Title - Author Name
   For example: # Ultimate Guide To Scar Treatments - Amanda Keyes
   If the author is not known from the content or metadata, write: # Document Title - Unknown author
   IMPORTANT: Clean up the title — remove version markers, revision dates, words like "FINAL", "DRAFT", "v2", "copy", revision numbers (e.g. "170123"), and trailing dashes or punctuation. The user should see a clean, readable title, not an internal file name.

2. **Description** (after the title): 2-3 sentences describing the file's content. Rational, neutral tone. Be specific and detailed — mention the most important facts, topics, names, amounts, dates found in the content. Use **bold** for key terms.
   AUTHOR IN DESCRIPTION: If you know the author, mention them naturally in the first sentence of the description — as if describing a book to a friend. For example: "This **611-page** collection of poetry by **Rumi** is a classic Arabic edition of the Mathnawi." or "Stephen King takes readers on a dark journey through New England in this **350-page** thriller." Do NOT just repeat the dry title format — weave the author into the description naturally.
   CRITICAL — PRESERVE PRECISE DETAILS: Always include exact numbers, ranges, substance names, ingredient lists, and specific values from the document. For example: if the text says "scars under 12 months old (with some guidance extending to 2 years)", write exactly that — do not simplify to "scars under a year". If specific nutrients are listed like "vitamin C, protein, zinc, and selenium", name them all. If timeframes are given like "9–12 months for the body and about 1 year for the face", include those exact ranges. Specific numbers, names, and precise data are the most valuable part of the description.
   NAME-DROP PRODUCTS, BRANDS, AND PEOPLE: When the document mentions specific brands, products, or notable people, USE THEM BY NAME — do not genericize. For example: write "RegimA Forte Scar Cream" instead of "a scar cream"; "Jane Iredale mineral makeup" instead of "mineral makeup for cover-up". This applies to medications (Accutane, Retin-A), tools (Photoshop, Figma), companies (Tesla, Google), people (Warren Buffett, Marie Curie), places (Mayo Clinic, MIT), products (iPhone 16, Model Y), and anything else with a proper name in the document content.
   MANDATORY MEASURABLE FACTS — in addition to the above, you MUST mention as many of these as possible (if present in the content):
   - Page/chapter/part count (e.g. "This **266-page** crime novel spans **12 chapters**")
   - All main character/person names, bolded (e.g. **Joanna Chyłka**, **Kordian Oryński**)
   - Key dates, years, time periods (e.g. "set in **2019**")
   - Places and locations (e.g. "events in **Warsaw** and near **Augustów**")
   - Amounts, percentages, statistics (e.g. "**$3.5M** in damages")
   - Organization, company, institution names
   - Dimensions, weights, distances, areas (e.g. "a **1,200 m²** plot", "a **42 km** route")
   - Measurements, lab values, reference ranges (e.g. "TSH **2.34 mIU/l** with ref range 0.27–4.20")
   - Identification numbers: tax IDs, contract numbers, case references, ISBNs
   - Deadlines, due dates, expiry dates (e.g. "payment due in **14 days**", "valid until **2027-03-01**")
   - Rankings, ratings, scores (e.g. "**4.8/5** stars", "**#3** on the bestseller list")
   - Sample sizes, participant counts (e.g. "study of **1,200 patients**")
   The more concrete, measurable facts — the better the description. Every sentence should contain at least one number, proper name, or measurable fact. The user should learn SPECIFIC things from the description, not generalities.
   If file metadata includes page_count, you MUST mention how many pages the document has (e.g. "This **14-page** scar treatment guide...").
   If an image was uploaded with EXIF metadata, mention the most interesting details (camera, date, GPS location).
   If the image shows a person or people, mention it.

3. **Expert insight** (after the description): 1-2 sentences with valuable expert analysis. This is the most important part — give the user something useful they might not notice on their own.
   Do NOT start with phrases like: "It's worth noting...", "The key takeaway is...", "What stands out...", "Importantly..." — these sound artificial.
   Instead, transition seamlessly into the substance, as if talking to a colleague. For example:
   - "The homocysteine level of 7.04 µmol/l falls within normal range, but it's useful to cross-reference with..."
   - "The net amount on this invoice doesn't account for..."
   - "This CV is missing a section on..."
   Adapt to the document type:
   - Lab results: flag values outside range, possible causes, suggested next steps (further tests, specialist visit).
   - Financial documents: highlight payment deadlines, irregularities, potential optimizations.
   - Legal documents: point out key clauses, risks, deadlines.
   - Articles/reports: surface the main thesis, a surprising finding, or broader context.
   - Photos: note something interesting about composition, technical details, or context.
   - Data/tables: point out a trend, anomaly, or the single most important number.

If file metadata is provided below (JSON block marked with =====), you MUST use it — e.g. author, creation date, title, camera info, etc.
NEVER mention internal technical metadata — skip information like: PDF generator name (e.g. "Skia/PDF", "Google Docs Renderer", "Microsoft Word", "LibreOffice", "wkhtmltopdf"), producer version, document ID, encoding format. This data is worthless to the user and reads like a system leak.

Write like a human briefly telling another human what this document is about — not like a machine generating a summary.
Be concise — this is a quick analysis, not an essay. Aim for roughly 150-250 words total (description + insight), using 1-4 paragraphs (usually 3, sometimes 2, rarely 4). Don't pad — every sentence must carry concrete value.
Do NOT ask the user anything. Do NOT use source markers like [1] or [source:1].
Occasionally use professional emoji to make the message more lively and scannable (e.g. ✅, 👌, 📄, 📊, 🔬, ⚠️, 💡, 📸, 🏥, ⚖️, 📝, 🔍, 📈, 🗓️, 💰, other light, fun, cool, non-offensive emoji). Do NOT overdo it — one or two per section is enough. Never use childish or unprofessional emoji (💩, 🤡, 😜, etc.).
Reply in the same language as the content.""" + _QUESTIONS_RULES_EN,
                ),
                ("human", "Uploaded files: {file_list}\n\nContent:\n{content}{metadata_section}"),
            ]
        )

    llm = get_llm()
    chain = prompt | llm | StrOutputParser()
    raw = _invoke_with_retry(
        chain,
        {"file_list": file_list, "content": combined, "metadata_section": metadata_section},
        label="describe",
    )
    welcome_message, suggested_questions = _parse_describe_response(raw)

    # Apply contextual post-processing (EXIF, person recognition, image prompts)
    if suggested_questions:
        from .suggested_questions import _append_contextual_prompts

        suggested_questions = _append_contextual_prompts(
            suggested_questions,
            file_names,
            file_types,
            language,
            welcome_message=welcome_message,
            description="",
        )

    return DescribeResult(
        welcome_message=welcome_message,
        suggested_questions=suggested_questions,
    )
