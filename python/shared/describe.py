from __future__ import annotations

import json
import logging
from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from .rag import get_llm
from .lang_detect import detect_language
from .extractors import clean_file_name

logger = logging.getLogger(__name__)


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
    msg = f"## {title}\n\n"
    if language == "pl":
        msg += f"Plik **{name_list}** został przesłany. Nie udało się wyodrębnić treści tekstowej — dokument może zawierać wyłącznie obrazy lub być zabezpieczony. Możesz zadać pytanie, a postaram się pomóc."
    else:
        msg += f"**{name_list}** has been uploaded. Text extraction was not possible — the document may contain only images or be protected. Feel free to ask a question and I'll do my best to help."
    return msg


# Keys to always exclude from the metadata block shown to the model
_META_EXCLUDE_KEYS = {"file_name", "file_created", "file_modified", "file_size_bytes", "exif", "web_detection", "identification", "producer", "creator"}

# ── Token budget for the describe prompt ─────────────────────────────
# Model context windows: gpt-4.1-mini ~1M, claude-3-5-haiku ~200K, gemma4 ~128K.
# We keep the content budget generous to cover large PDFs well while still
# fitting comfortably in all supported model context windows.
# ~30K tokens ≈ 120K chars is safe for all models and gives the LLM
# much more raw text to work with for detailed welcome messages.
_DESCRIBE_MAX_CONTENT_CHARS = 120_000
# When a document is large, we split the budget: 50% for raw text from start,
# 20% for 2-pass summaries of remaining content, 30% for page summaries.
_TEXT_BUDGET_RATIO = 0.50
_SUMMARY_PASS_BUDGET_RATIO = 0.20
# Threshold for triggering 2-pass summarization (chars of total extracted text)
_TWO_PASS_THRESHOLD = 200_000


def _estimate_total_text_len(extracted: list[dict]) -> int:
    """Return the total character count across all extracted documents."""
    return sum(len(doc.get("text") or "") for doc in extracted)


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

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_msg),
        ("human", f"Document section ({chunk_label}):\n\n{{text}}"),
    ])

    llm = get_llm()
    chain = prompt | llm | StrOutputParser()
    result = chain.invoke({"text": text})
    logger.info(f"📝 2-pass summary for {chunk_label}: {len(text)} chars → {len(result)} chars")
    return result.strip()


def describe_documents(
    extracted: list[dict],
    images: list[dict],
    language: str | None = None,
    file_metadata: dict[str, dict] | None = None,
    page_summaries: list[dict] | None = None,
) -> str:
    """Generate a welcome message with a ## Title, description, and expert insight.

    Uses the beginning of extracted text (no embeddings/RAG) so the response
    is as quick as possible.  When file_metadata contains EXIF data for images,
    it is included so the welcome message can mention camera, date, location etc.

    For very large documents the full text would exceed model limits, so we
    use a hybrid strategy: truncated beginning of text + short per-page
    summaries, staying within ``_DESCRIBE_MAX_CONTENT_CHARS``.
    """
    total_chars = _estimate_total_text_len(extracted)
    is_large = total_chars > _DESCRIBE_MAX_CONTENT_CHARS and page_summaries

    # ── Build image snippets (always included, capped) ───────────────
    image_snippets: list[str] = []
    for img in images:
        desc = img.get("description", "")
        name = clean_file_name(img.get("file_name", "image"))
        page = img.get("page", "?")
        if desc:
            image_snippets.append(f"[Image from {name}, page {page}]\n{desc[:500]}")
    image_block = "\n\n---\n\n".join(image_snippets)

    if is_large:
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
            # Detect language early for summarization prompts
            early_lang = language or detect_language(
                (extracted[0].get("text") or "")[:2000] if extracted else ""
            )
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
                summary_1 = _summarize_text_chunk(first_half, "first half (middle pages)", early_lang)
                summary_2 = _summarize_text_chunk(second_half, "second half (final pages)", early_lang)
                
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
            return _fallback_from_metadata(extracted, images, file_metadata, language)
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
            return _fallback_from_metadata(extracted, images, file_metadata, language)

        combined = "\n\n---\n\n".join(snippets)[:_DESCRIBE_MAX_CONTENT_CHARS]

    # Build a metadata block from file_metadata (EXIF, PDF info, etc.)
    # Only include files that have meaningful metadata beyond basic file stats.
    metadata_block = ""
    if file_metadata:
        meta_parts: list[str] = []
        for fname, meta in file_metadata.items():
            try:
                useful = {k: v for k, v in meta.items() if k not in _META_EXCLUDE_KEYS and v}
                if useful:
                    meta_parts.append(f"[{fname}]\n{json.dumps(useful, ensure_ascii=False, default=str)}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to format metadata for {fname}: {e}")
        if meta_parts:
            metadata_block = "\n\n".join(meta_parts)

    if language is None:
        language = detect_language(combined[:2000])

    file_names = [clean_file_name(doc.get("file_name", "")) for doc in extracted]
    file_names += [clean_file_name(img.get("file_name", "")) for img in images]
    file_list = ", ".join(dict.fromkeys(fn for fn in file_names if fn))

    if language == "pl":
        prompt = ChatPromptTemplate.from_messages([
            ("system", """Tworzysz wiadomość powitalną, którą zobaczy użytkownik zaraz po przesłaniu pliku.
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
   Sformatuj jako nagłówek Markdown: ## Tytuł dokumentu - Imię Nazwisko Autora
   Na przykład: ## Przewodnik po bliznach - Amanda Keyes
   Jeśli autor nie jest znany z treści ani metadanych, napisz: ## Tytuł dokumentu - Nieznany autor
   WAŻNE: Oczyść tytuł z artefaktów technicznych — usuń oznaczenia wersji, daty rewizji, słowa typu "FINAL", "DRAFT", "v2", "copy", numery rewizji (np. "170123"), myślniki i znaki na końcu. Użytkownik powinien zobaczyć czysty, czytelny tytuł, nie wewnętrzną nazwę pliku.

2. **Opis** (po tytule): 2-4 zdania opisujące zawartość pliku. Racjonalny, neutralny ton. Bądź konkretny i szczegółowy — wymień najważniejsze fakty, tematy, nazwiska, kwoty, daty znalezione w treści. Używaj **pogrubienia** dla kluczowych terminów.
   KLUCZOWE — ZACHOWAJ PRECYZYJNE SZCZEGÓŁY: Zawsze podawaj dokładne liczby, zakresy, nazwy substancji, składników, terminów i konkretne wartości z dokumentu. Na przykład: jeśli tekst mówi o "bliznach do 12 miesięcy (z zaleceniami do 2 lat)", napisz właśnie tak — nie upraszczaj do "blizny do roku". Jeśli wymienione są konkretne składniki jak "witamina C, białko, cynk i selen", wymień je wszystkie. Jeśli podane są zakresy czasowe jak "9–12 miesięcy dla ciała i około 1 rok dla twarzy", podaj te dokładne przedziały. Szczegółowe dane liczbowe i nazwy własne to najcenniejsza informacja w opisie.
   Jeśli w metadanych pliku jest pole page_count, KONIECZNIE wspomnij ile stron liczy dokument (np. "Ten **14-stronicowy** przewodnik...").
   Jeśli przesłano zdjęcie z metadanymi EXIF, wspomnij najciekawsze szczegóły (aparat, data, lokalizacja).
   Jeśli na zdjęciu widać osobę lub ludzi, napisz o tym.

3. **Ekspercki wgląd** (po opisie): 2-3 zdania z wartościową analizą eksperta. To najważniejsza część — musisz dać użytkownikowi coś przydatnego, czego sam mógłby nie zauważyć.
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
Bądź zwięzły — to ma być szybka analiza, nie rozprawka.
NIE pytaj użytkownika o nic. NIE używaj odnośników źródłowych jak [1] ani [source:1].
Od czasu do czasu użyj profesjonalnych emoji, żeby wiadomość była bardziej żywa i łatwa do przeskanowania (np. ✅, 👌, 📄, 📊, 🔬, ⚠️, 💡, 📸, 🏥, ⚖️, 📝, 🔍, 📈, 🗓️, 💰). Nie przesadzaj — jedno-dwa na sekcję wystarczą. Nigdy nie używaj dziecinnych lub nieprofesjonalnych emoji (💩, 🤡, 😜 itp.).
Odpowiadaj po polsku."""),
            ("human", "Przesłane pliki: {file_list}\n\nTreść:\n{content}{metadata_section}"),
        ])
    else:
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are writing a welcome message that a human user will see right after uploading a file.
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
   Format as a Markdown heading: ## Document Title - Author Name
   For example: ## Ultimate Guide To Scar Treatments - Amanda Keyes
   If the author is not known from the content or metadata, write: ## Document Title - Unknown author
   IMPORTANT: Clean up the title — remove version markers, revision dates, words like "FINAL", "DRAFT", "v2", "copy", revision numbers (e.g. "170123"), and trailing dashes or punctuation. The user should see a clean, readable title, not an internal file name.

2. **Description** (after the title): 2-4 sentences describing the file's content. Rational, neutral tone. Be specific and detailed — mention the most important facts, topics, names, amounts, dates found in the content. Use **bold** for key terms.
   CRITICAL — PRESERVE PRECISE DETAILS: Always include exact numbers, ranges, substance names, ingredient lists, and specific values from the document. For example: if the text says "scars under 12 months old (with some guidance extending to 2 years)", write exactly that — do not simplify to "scars under a year". If specific nutrients are listed like "vitamin C, protein, zinc, and selenium", name them all. If timeframes are given like "9–12 months for the body and about 1 year for the face", include those exact ranges. Specific numbers, names, and precise data are the most valuable part of the description.
   If file metadata includes page_count, you MUST mention how many pages the document has (e.g. "This **14-page** scar treatment guide...").
   If an image was uploaded with EXIF metadata, mention the most interesting details (camera, date, GPS location).
   If the image shows a person or people, mention it.

3. **Expert insight** (after the description): 2-3 sentences with valuable expert analysis. This is the most important part — give the user something useful they might not notice on their own.
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
Be concise — this is a quick analysis, not an essay.
Do NOT ask the user anything. Do NOT use source markers like [1] or [source:1].
Occasionally use professional emoji to make the message more lively and scannable (e.g. ✅, 👌, 📄, 📊, 🔬, ⚠️, 💡, 📸, 🏥, ⚖️, 📝, 🔍, 📈, 🗓️, 💰). Do NOT overdo it — one or two per section is enough. Never use childish or unprofessional emoji (💩, 🤡, 😜, etc.).
Reply in the same language as the content."""),
            ("human", "Uploaded files: {file_list}\n\nContent:\n{content}{metadata_section}"),
        ])

    # Build the metadata section — only include if we have actual metadata
    metadata_section = ""
    if metadata_block:
        metadata_section = f"\n\n=====\nFile metadata (from EXIF / PDF info):\n{metadata_block}\n====="

    llm = get_llm()
    chain = prompt | llm | StrOutputParser()
    result = chain.invoke({"file_list": file_list, "content": combined, "metadata_section": metadata_section})
    return result.strip()
