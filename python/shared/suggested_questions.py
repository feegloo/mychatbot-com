from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from .config import get_settings


def suggest_questions_from_chunks(chunks: list[str]) -> list[str]:
    settings = get_settings()

    # Use stratified sampling to capture diverse topics throughout the document
    # instead of just the first few chunks
    if len(chunks) <= 8:
        sample_chunks = chunks
    else:
        # Sample chunks from beginning, middle, and end of document
        import math
        indices = set()
        # Always include first few chunks
        indices.update(range(min(3, len(chunks))))
        # Sample from middle section
        mid_start = len(chunks) // 3
        mid_end = 2 * len(chunks) // 3
        step = max(1, (mid_end - mid_start) // 2)
        indices.update(range(mid_start, mid_end, step))
        # Always include last few chunks
        indices.update(range(max(0, len(chunks) - 3), len(chunks)))
        
        sorted_indices = sorted(list(indices))[:8]
        sample_chunks = [chunks[i] for i in sorted_indices]
    
    sample = "\n\n".join(sample_chunks)[:10000]  # Increased from 9000 to 10000 for better coverage
    prompt = ChatPromptTemplate.from_template(
        """
        Generate exactly 4 concise, useful questions a user might ask about the following uploaded content.

        Rules:
        - Each question should be on its own line
        - No numbering
        - No extra explanation
        - Questions should be natural and clickable in a UI
        - Cover different topics/sections mentioned in the content

        Content:
        {content}
        """
    )

    llm = ChatOpenAI(model=settings.openai_chat_model, temperature=0, api_key=settings.openai_api_key)
    chain = prompt | llm | StrOutputParser()
    response = chain.invoke({"content": sample})
    questions = [line.strip("- ").strip() for line in response.splitlines() if line.strip()]
    return questions[:4]
