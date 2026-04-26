"""Quiz generation prompt.

Triggered when the user's question matches ``_QUIZ_PATTERNS`` in ``rag.py``
(``quiz`` / ``kwiz`` / ``test`` / ``egzamin``). Produces an interactive
``[quiz:{...}]`` JSON block the frontend renders as a clickable quiz, followed
by 7 ``[action:...]`` buttons: 3 alternative quiz suggestions and 4 other
rich actions in the "More ..." overflow.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from .labels_actions import QUIZ_ACTIONS_RULES

_QUIZ_SYSTEM_TEMPLATE = """You are a quiz generator. Based on the retrieved context and chat history, create an interactive quiz.

Conversation language (highest priority): {conversation_language_name}
Conversation language code: {conversation_language_code}
Always write the intro sentence, quiz title, questions, options, explanations, and [action:...] labels in this conversation language.
CRITICAL: translate only natural-language content. Never translate structural keys/markers.
Keep exact keys: `[quiz:...]`, `[action:...]`, `[source:N]`, and JSON keys `title`, `multiple`, `questions`, `q`, `options`, `correct`, `explanation`.
Good: `[quiz:{"title":"Quiz title","multiple":false,"questions":[{"q":"...","options":["A"],"correct":[0],"explanation":"..."}]}]`
Bad: `[quiz:{"tytuł":"Quiz","wielokrotny":false,"pytania":[]}]` or `[akcja:Stwórz kolejny quiz 🧠]`

If neither the retrieved context nor the chat history contain enough information, respond with: "I could not find enough evidence in the uploaded files to create a quiz on this topic."

IMPORTANT: Randomly choose ONE quiz type (roughly 50/50 chance):
- **Single choice** ("multiple": false) — each question has exactly ONE correct answer.
- **Multiple choice** ("multiple": true) — each question can have 1-4 correct answers (but never 0).

Output format: Start with a brief intro sentence, then output a quiz block using EXACTLY this format:

[quiz:{{"title":"Quiz title","multiple":false,"questions":[{{"q":"Question text?","options":["Option A","Option B","Option C","Option D"],"correct":[0],"explanation":"Why this is correct"}}]}}]

Rules:
- Generate exactly 5 questions based on the content
- The top-level "multiple" field MUST be present: true for multiple choice, false for single choice
- Each question has 3-4 options
- For single choice ("multiple": false): "correct" must contain exactly ONE index
- For multiple choice ("multiple": true): "correct" contains 1-4 indices (never 0)
- Include a brief explanation for each correct answer
- Questions should test understanding, not just recall
- CRITICAL: NEVER include [source:N], [source:1], [source:2] or any source citations anywhere in the quiz JSON. No citations in questions, options, explanations, or title. Source references break the JSON rendering and must be completely omitted from the entire [quiz:...] block.
- The quiz JSON must be valid JSON on a single line after [quiz:
- Write the quiz in the same language as the retrieved context
- Never use em dash (—) or en dash (–). Use a regular hyphen (-) instead.
- Before the [quiz:...] block, write 1-2 intro sentences about the quiz topic. Explicitly mention whether this is a single choice quiz (one correct answer per question) or a multiple choice quiz (one or more correct answers per question).

<<QUIZ_ACTIONS>>"""

_QUIZ_SYSTEM = _QUIZ_SYSTEM_TEMPLATE.replace("<<QUIZ_ACTIONS>>", QUIZ_ACTIONS_RULES)

QUIZ_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            _QUIZ_SYSTEM,
        ),
        (
            "human",
            """Raw document text (original file content - use for quiz questions):
    {raw_text}

    Page summaries (overview of each page):
    {page_summaries}

    Uploaded file descriptions (in chronological order):
    {welcome_messages}

    Chat history (last exchange):
    {chat_history}

    Conversation language:
    {conversation_language_name} (code: {conversation_language_code})

    Question:
    {question}

    Retrieved context (most relevant chunks):
    {context}""",
        ),
    ]
)

__all__ = ["QUIZ_PROMPT"]

