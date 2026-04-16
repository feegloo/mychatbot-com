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
    """Generate a welcome message with a ### Title and 2-4 sentence description.

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
Ta wiadomość będzie czytana przez zwykłego człowieka — powinna brzmieć naturalnie, przyjaźnie i pomocnie.

Twoja odpowiedź MUSI składać się z dwóch części:

1. **Tytuł** (pierwsza linia): Krótkie podsumowanie przesłanego pliku — tytuł, autor/źródło i rok jeśli znane.
   Sformatuj jako nagłówek Markdown: ### Tytuł tutaj
   
2. **Opis** (po tytule): 2-4 zdania opisujące zawartość pliku. Bądź konkretny — wymień najważniejsze fakty, tematy, nazwiska lub kwoty znalezione w treści. Używaj **pogrubienia** dla kluczowych terminów.
   Jeśli przesłano zdjęcie z metadanymi EXIF, wspomnij najciekawsze szczegóły (aparat, data, lokalizacja).
   Jeśli na zdjęciu widać osobę lub ludzi, napisz o tym.

Jeśli podano metadane pliku (JSON poniżej oznaczony =====), KONIECZNIE wykorzystaj je — np. autora, datę utworzenia, producenta, tytuł, aparat itp.

Pisz jak człowiek, który opisuje dokument innemu człowiekowi — nie jak automat generujący streszczenie.
NIE pytaj użytkownika o nic. NIE używaj odnośników źródłowych jak [1] ani [source:1].
Odpowiadaj po polsku."""),
            ("human", "Przesłane pliki: {file_list}\n\nTreść:\n{content}{metadata_section}"),
        ])
    else:
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are writing a welcome message that a human user will see right after uploading a file.
This message will be read by a real person — it should sound natural, friendly, and helpful.

Your response MUST have two parts:

1. **Title** (first line): A short summary of the uploaded file — its title, author/source, and year if known.
   Format as a Markdown heading: ### Title here
   
2. **Description** (after the title): 2-4 sentences describing the file's content. Be specific — mention the most important facts, topics, names, or amounts found in the content. Use **bold** for key terms.
   If an image was uploaded with EXIF metadata, mention the most interesting details (camera, date, GPS location).
   If the image shows a person or people, mention it.

If file metadata is provided below (JSON block marked with =====), you MUST use it — e.g. author, creation date, producer, title, camera info, etc.

Write like a human briefly telling another human what this document is about — not like a machine generating a summary.
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
