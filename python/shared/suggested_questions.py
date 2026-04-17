from __future__ import annotations

import json
import logging

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from .rag import get_llm
from .lang_detect import detect_language
from .extractors import clean_file_name

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
    file_names: list[str] = None,
    file_types: dict[str, str] = None,
    welcome_message: str = "",
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
- Pierwsze 3 to naturalne pytania o treść dokumentu (krótkie, konkretne, klikalne) — BEZ emoji
- Ostatnie 2 to kreatywne/kontekstowe prompty-akcje w formie: "<temat z dokumentu> - <akcja>"
  Przykładowe akcje: "stwórz diagram mermaid", "napisz wiersz", "napisz podobny", "stwórz quiz", "napisz podsumowanie", "stwórz tabelę porównawczą", "napisz email", "wyjaśnij jak dla dziecka"
  Wybierz akcje które najlepiej pasują do treści dokumentu.
  Każdy prompt-akcja MUSI kończyć się odpowiednim emoji (🖼️ dla diagramu mermaid, ✏️ dla pisania, 🧠 dla quizu, 📝 dla podsumowania, 📋 dla listy, ✅ dla checklisty, 🎭 dla wiersza, 📧 dla emaila, 👶 dla wyjaśnienia)
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
- First 3 are natural questions about the document content (short, specific, clickable) — NO emoji
- Last 2 are creative/contextual action-prompts in the form: "<topic from document> - <action>"
  Example actions: "create mermaid diagram", "write poem", "write similar", "create quiz", "write summary", "create comparison table", "write email", "explain like I'm 5"
  Pick actions that best fit the document's content.
  Each action-prompt MUST end with a relevant emoji (🖼️ for mermaid diagram, ✏️ for writing, 🧠 for quiz, 📝 for summary, 📋 for checklist, ✅ for checklist, 🎭 for poem, 📧 for email, 👶 for ELI5)
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
            return _append_contextual_prompts(questions[:5], file_names, file_types, language, welcome_message)
    except (json.JSONDecodeError, AttributeError):
        logger.warning(f"Failed to parse JSON from suggested questions response, falling back to line parsing")

    # Fallback: parse as lines (backward compat)
    questions = [line.strip("- ").strip() for line in response.splitlines() if line.strip()]
    return _append_contextual_prompts(questions[:5], file_names, file_types, language, welcome_message)


import re

_PERSON_PATTERN = re.compile(
    r'\b(person|people|man|woman|portrait|face|selfie|human|'
    r'osoba|osoby|mężczyzna|kobieta|twarz|portret|człowiek|ludzie|'
    r'depicts? a|shows? a|presents? a|przedstawia)\b',
    re.IGNORECASE,
)

_INGREDIENT_PATTERN = re.compile(
    r'\b(ingredient|ingredients|składnik|składniki|skład|composition|'
    r'contains|zawiera|nutrition|wartości odżywcze|product label|etykiet)\b',
    re.IGNORECASE,
)


def _append_contextual_prompts(
    questions: list[str],
    file_names: list[str] | None,
    file_types: dict[str, str] | None,
    language: str | None,
    welcome_message: str = "",
) -> list[str]:
    """Build final list: 3 normal questions + up to 2 action prompts = max 5.
    
    Contextual action prompts (EXIF, recognize, file metadata) take priority
    over LLM-generated action prompts. 'recognize person name' is only added when
    the welcome message indicates a person is visible in the image.
    'create recipe' is added when the welcome message mentions ingredients.
    """
    # Split LLM output: first 3 are questions, rest are actions
    normal_questions = questions[:3]
    llm_actions = questions[3:5]

    # Build contextual action prompts (higher priority than LLM actions)
    contextual: list[str] = []
    if file_names and file_types:
        has_person = bool(_PERSON_PATTERN.search(welcome_message))
        has_ingredients = bool(_INGREDIENT_PATTERN.search(welcome_message))

        for name in file_names:
            if len(contextual) >= 2:
                break
            ftype = file_types.get(name, "document")
            display_name = clean_file_name(name)
            short_name = display_name if len(display_name) <= 30 else display_name[:27] + "..."

            if ftype == "image":
                if has_ingredients and len(contextual) < 2:
                    if language == "pl":
                        contextual.append(f"{short_name} - stwórz przepis 🍝")
                    else:
                        contextual.append(f"{short_name} - create recipe 🍝")
                if len(contextual) < 2:
                    if language == "pl":
                        contextual.append(f"{short_name} - pokaż metadane EXIF 📷")
                        if has_person and len(contextual) < 2:
                            contextual.append(f"{short_name} - rozpoznaj osobę 🔍")
                    else:
                        contextual.append(f"{short_name} - show EXIF metadata 📷")
                        if has_person and len(contextual) < 2:
                            contextual.append(f"{short_name} - recognize person name 🔍")
            elif ftype == "pdf":
                if language == "pl":
                    contextual.append(f"{short_name} - pokaż metadane pliku 📄")
                else:
                    contextual.append(f"{short_name} - show file metadata 📄")

    # Fill remaining action slots with LLM-generated actions
    remaining_slots = 2 - len(contextual)
    actions = llm_actions[:remaining_slots] + contextual

    return normal_questions + actions
