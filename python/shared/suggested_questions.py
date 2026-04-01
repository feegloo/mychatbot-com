from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from .config import get_settings


def suggest_questions_from_chunks(chunks: list[str]) -> list[str]:
    settings = get_settings()

    sample = "\n\n".join(chunks[:8])[:9000]
    prompt = ChatPromptTemplate.from_template(
        """
        Generate exactly 4 concise, useful questions a user might ask about the following uploaded content.

        Rules:
        - Each question should be on its own line
        - No numbering
        - No extra explanation
        - Questions should be natural and clickable in a UI

        Content:
        {content}
        """
    )

    llm = ChatOpenAI(model=settings.openai_chat_model, temperature=0, api_key=settings.openai_api_key)
    chain = prompt | llm | StrOutputParser()
    response = chain.invoke({"content": sample})
    questions = [line.strip("- ").strip() for line in response.splitlines() if line.strip()]
    return questions[:4]
