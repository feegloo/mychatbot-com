from __future__ import annotations

import logging
from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from .rag import get_llm
from .lang_detect import detect_language

logger = logging.getLogger(__name__)


def describe_documents(
    extracted: list[dict],
    images: list[dict],
    language: str | None = None,
    file_metadata: dict[str, dict] | None = None,
) -> str:
    """Generate a 1-3 sentence FAST description of what was uploaded.

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

    # Append EXIF metadata for image files
    if file_metadata:
        for fname, meta in file_metadata.items():
            if meta.get("file_type") != "image":
                continue
            exif_lines = []
            for key, label in [
                ("camera_make", "Camera"),
                ("camera_model", "Model"),
                ("date_taken", "Date taken"),
                ("gps_latitude", "GPS lat"),
                ("gps_longitude", "GPS lon"),
                ("image_width", "Width"),
                ("image_height", "Height"),
                ("iso", "ISO"),
                ("f_number", "f/"),
                ("exposure_time", "Exposure"),
                ("focal_length", "Focal length"),
                ("lens_model", "Lens"),
                ("artist", "Artist"),
                ("copyright", "Copyright"),
                ("software", "Software"),
            ]:
                if key in meta:
                    exif_lines.append(f"  {label}: {meta[key]}")
            if exif_lines:
                snippets.append(f"[EXIF metadata for {fname}]\n" + "\n".join(exif_lines))

    if not snippets:
        return ""

    combined = "\n\n---\n\n".join(snippets)[:6000]

    if language is None:
        language = detect_language(combined[:2000])

    file_names = [doc.get("file_name", "") for doc in extracted]
    file_names += [img.get("file_name", "") for img in images]
    file_list = ", ".join(dict.fromkeys(fn for fn in file_names if fn))

    if language == "pl":
        prompt = ChatPromptTemplate.from_messages([
            ("system", """Wygeneruj BARDZO krótki opis (1-3 zdania) tego, co użytkownik właśnie przesłał.
Bądź konkretny – wymień kluczowe fakty (np. kwoty, daty, nazwiska, tematy) znalezione w treści.
Jeśli przesłano zdjęcie i dostępne są metadane EXIF, wymień najciekawsze z nich (np. aparat, data, lokalizacja GPS).
Jeśli na zdjęciu widać osobę lub ludzi, napisz o tym wprost (np. "zdjęcie przedstawia osobę", "na zdjęciu widać mężczyznę/kobietę").
NIE pytaj użytkownika o nic. NIE używaj oznaczników źródłowych jak [1] ani [source:1].
Odpowiadaj po polsku. Opis powinien brzmieć naturalnie, jakbyś opisywał komuś co to za dokument."""),
            ("human", "Przesłane pliki: {file_list}\n\nTreść:\n{content}"),
        ])
    else:
        prompt = ChatPromptTemplate.from_messages([
            ("system", """Generate a VERY short description (1-3 sentences) of what the user just uploaded.
Be specific – mention key facts (e.g. amounts, dates, names, topics) found in the content.
If an image was uploaded with EXIF metadata, mention the most interesting details (e.g. camera, date taken, GPS location).
If the image shows a person or people, state this explicitly (e.g. "the photo shows a person", "the image depicts a man/woman").
Do NOT ask the user anything. Do NOT use source markers like [1] or [source:1].
Reply in the same language as the content. The description should sound natural, as if you are briefly telling someone what this document is about."""),
            ("human", "Uploaded files: {file_list}\n\nContent:\n{content}"),
        ])

    llm = get_llm()
    chain = prompt | llm | StrOutputParser()
    result = chain.invoke({"file_list": file_list, "content": combined})
    return result.strip()
