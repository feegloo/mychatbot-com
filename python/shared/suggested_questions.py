from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from .rag import get_llm


from .lang_detect import detect_language

def suggest_questions_from_chunks(chunks: list[str], language: str = None) -> list[str]:

    # Use stratified sampling to capture diverse topics throughout the document
    if len(chunks) <= 8:
        sample_chunks = chunks
    else:
        import math
        indices = set()
        indices.update(range(min(3, len(chunks))))
        mid_start = len(chunks) // 3
        mid_end = 2 * len(chunks) // 3
        step = max(1, (mid_end - mid_start) // 2)
        indices.update(range(mid_start, mid_end, step))
        indices.update(range(max(0, len(chunks) - 3), len(chunks)))
        sorted_indices = sorted(list(indices))[:8]
        sample_chunks = [chunks[i] for i in sorted_indices]

    sample = "\n\n".join(sample_chunks)[:10000]

    # Detect language if not provided
    if language is None:
        # Use the first 2000 chars for detection
        text_for_lang = sample[:2000]
        language = detect_language(text_for_lang)

    # Language-specific prompt
    if language == "pl":
        prompt = ChatPromptTemplate.from_template(
            """
            Wygeneruj dokładnie 4 zwięzłe, przydatne pytania, które użytkownik mógłby zadać na podstawie poniższej treści.

            Zasady:
            - Każde pytanie w osobnej linii
            - Bez numeracji
            - Bez dodatkowych wyjaśnień
            - Pytania powinny być naturalne i klikalne w interfejsie
            - Obejmij różne tematy/sekcje z treści
            - Wygeneruj tylko takie pytania, na które można znaleźć odpowiedź w treści, nie wymyślaj pytań, które nie mają podstaw w tekście

            Treść:
            {content}
            """
        )
    else:
        prompt = ChatPromptTemplate.from_template(
            """
            Generate exactly 4 concise, useful questions a user might ask about the following uploaded content.

            Rules:
            - Each question should be on its own line
            - No numbering
            - No extra explanation
            - Questions should be natural and clickable in a UI
            - Cover different topics/sections mentioned in the content
            - Only generate questions that can be answered based on the content, do not make up questions that are not grounded in the text

            Content:
            {content}
            """
        )

    llm = get_llm()
    chain = prompt | llm | StrOutputParser()
    response = chain.invoke({"content": sample})
    questions = [line.strip("- ").strip() for line in response.splitlines() if line.strip()]
    return questions[:4]
