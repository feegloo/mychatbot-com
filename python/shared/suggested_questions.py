from __future__ import annotations

import json
import logging

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from .rag import get_llm
from .lang_detect import detect_language

logger = logging.getLogger(__name__)


def _sample_chunks(chunks: list[str], max_chunks: int = 8) -> list[str]:
    """Stratified sampling to capture diverse topics throughout the document."""
    if len(chunks) <= max_chunks:
        return chunks

    indices = set()
    indices.update(range(min(3, len(chunks))))
    mid_start = len(chunks) // 3
    mid_end = 2 * len(chunks) // 3
    step = max(1, (mid_end - mid_start) // 2)
    indices.update(range(mid_start, mid_end, step))
    indices.update(range(max(0, len(chunks) - 3), len(chunks)))
    sorted_indices = sorted(list(indices))[:max_chunks]
    return [chunks[i] for i in sorted_indices]


def suggest_questions_from_chunks(
    chunks: list[str],
    language: str = None,
    description: str = "",
) -> list[str]:
    sample_chunks = _sample_chunks(chunks)
    sample = "\n\n".join(sample_chunks)[:10000]

    # Detect language if not provided
    if language is None:
        text_for_lang = sample[:2000]
        language = detect_language(text_for_lang)

    # --- Generate 3 natural questions + 2 contextual/creative prompts in one call ---
    if language == "pl":
        prompt = ChatPromptTemplate.from_messages([
            ("system", """Wygeneruj DOKŁADNIE 5 sugerowanych promptów dla użytkownika na podstawie poniższej treści.

Odpowiedz WYŁĄCZNIE prawidłowym JSON-em (bez markdown, bez ```json). Format:
{{"questions": ["q1", "q2", "q3", "q4", "q5"]}}

Zasady:
- Pierwsze 3 to naturalne pytania o treść dokumentu (krótkie, konkretne, klikalne)
- Ostatnie 2 to kreatywne/kontekstowe prompty w formie: "<temat z dokumentu> — <akcja>"
  Przykładowe akcje: "stwórz diagram", "napisz wiersz", "napisz podobny", "stwórz quiz", "napisz podsumowanie", "stwórz tabelę porównawczą", "napisz email", "wyjaśnij jak dla dziecka"
  Wybierz akcje które najlepiej pasują do treści dokumentu.
- Każdy prompt powinien być zwięzły (max 10 słów)
- NIE numeruj, NIE dodawaj wyjaśnień

Opis dokumentu: {description}"""),
            ("human", "{content}"),
        ])
    else:
        prompt = ChatPromptTemplate.from_messages([
            ("system", """Generate EXACTLY 5 suggested prompts for the user based on the following uploaded content.

Reply with ONLY valid JSON (no markdown, no ```json). Format:
{{"questions": ["q1", "q2", "q3", "q4", "q5"]}}

Rules:
- First 3 are natural questions about the document content (short, specific, clickable)
- Last 2 are creative/contextual prompts in the form: "<topic from document> — <action>"
  Example actions: "create diagram", "write poem", "write similar", "create quiz", "write summary", "create comparison table", "write email", "explain like I'm 5"
  Pick actions that best fit the document's content.
- Each prompt should be concise (max 10 words)
- Do NOT number, do NOT add explanations

Document description: {description}"""),
            ("human", "{content}"),
        ])

    llm = get_llm()
    chain = prompt | llm | StrOutputParser()
    response = chain.invoke({"content": sample, "description": description})

    # Parse JSON response
    try:
        parsed = json.loads(response.strip())
        questions = parsed.get("questions", [])
        if isinstance(questions, list) and len(questions) >= 3:
            return questions[:5]
    except (json.JSONDecodeError, AttributeError):
        logger.warning(f"Failed to parse JSON from suggested questions response, falling back to line parsing")

    # Fallback: parse as lines (backward compat)
    questions = [line.strip("- ").strip() for line in response.splitlines() if line.strip()]
    return questions[:5]
