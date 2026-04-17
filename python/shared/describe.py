from __future__ import annotations

import json
import logging
from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from .rag import get_llm
from .lang_detect import detect_language

logger = logging.getLogger(__name__)


# Keys to always exclude from the metadata block shown to the model
_META_EXCLUDE_KEYS = {"file_name", "file_created", "file_modified", "file_size_bytes", "exif", "web_detection", "identification"}


def describe_documents(
    extracted: list[dict],
    images: list[dict],
    language: str | None = None,
    file_metadata: dict[str, dict] | None = None,
) -> str:
    """Generate a welcome message with a ## Title, description, and expert insight.

    Uses the beginning of extracted text (no embeddings/RAG) so the response
    is as quick as possible.  When file_metadata contains EXIF data for images,
    it is included so the welcome message can mention camera, date, location etc.
    """
    # Build a concise snippet from the beginning of each document
    snippets: list[str] = []
    for doc in extracted:
        name = doc.get("file_name", "unknown")
        text = (doc.get("text") or "")[:3000]
        if text.strip():
            snippets.append(f"[File: {name}]\n{text}")

    for img in images:
        desc = img.get("description", "")
        name = img.get("file_name", "image")
        page = img.get("page", "?")
        if desc:
            snippets.append(f"[Image from {name}, page {page}]\n{desc[:500]}")

    if not snippets:
        return ""

    combined = "\n\n---\n\n".join(snippets)[:6000]

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

    file_names = [doc.get("file_name", "") for doc in extracted]
    file_names += [img.get("file_name", "") for img in images]
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

1. **Tytuł** (pierwsza linia): Krótkie podsumowanie przesłanego pliku — tytuł, autor/źródło i rok jeśli znane.
   Sformatuj jako nagłówek Markdown: ## Tytuł tutaj

2. **Opis** (po tytule): 2-4 zdania opisujące zawartość pliku. Racjonalny, neutralny ton. Bądź konkretny i szczegółowy — wymień najważniejsze fakty, tematy, nazwiska, kwoty, daty znalezione w treści. Używaj **pogrubienia** dla kluczowych terminów.
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

Jeśli podano metadane pliku (JSON poniżej oznaczony =====), KONIECZNIE wykorzystaj je — np. autora, datę utworzenia, producenta, tytuł, aparat itp.

Pisz jak człowiek, który opisuje dokument innemu człowiekowi — nie jak automat generujący streszczenie.
Bądź zwięzły — to ma być szybka analiza, nie rozprawka.
NIE pytaj użytkownika o nic. NIE używaj odnośników źródłowych jak [1] ani [source:1].
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

1. **Title** (first line): A short summary of the uploaded file — its title, author/source, and year if known.
   Format as a Markdown heading: ## Title here

2. **Description** (after the title): 2-4 sentences describing the file's content. Rational, neutral tone. Be specific and detailed — mention the most important facts, topics, names, amounts, dates found in the content. Use **bold** for key terms.
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

If file metadata is provided below (JSON block marked with =====), you MUST use it — e.g. author, creation date, producer, title, camera info, etc.

Write like a human briefly telling another human what this document is about — not like a machine generating a summary.
Be concise — this is a quick analysis, not an essay.
Do NOT ask the user anything. Do NOT use source markers like [1] or [source:1].
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
