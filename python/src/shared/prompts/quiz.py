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
Good: `[quiz:{{"title":"Quiz title","multiple":false,"questions":[{{"q":"...","options":["A"],"correct":[0],"explanation":"..."}}]}}]`
Bad: `[quiz:{{"tytuł":"Quiz","wielokrotny":false,"pytania":[]}}]` or `[akcja:Stwórz kolejny quiz 🧠]`

If neither the retrieved context nor the chat history contain enough information, respond with: "I could not find enough evidence in the uploaded files to create a quiz on this topic."

IMPORTANT — Quiz type selection (read the user's question carefully FIRST):
1. If the user's question explicitly requests **multiple choice** (e.g. "multiple choice quiz", "wielokrotnego wyboru", "wielokrotny wybór", "multi-choice", "mehrere richtige", "choix multiple", "опрос с несколькими ответами", or any translation meaning "more than one correct answer"), you MUST set "multiple": true.
2. If the user's question explicitly requests **single choice** (e.g. "single choice quiz", "jednokrotnego wyboru", "jednokrotny wybór", "one correct answer", "nur eine richtige", "choix unique", "один правильный ответ", or any translation meaning "exactly one correct answer"), you MUST set "multiple": false.
3. Only when the user gives NO hint about quiz type: randomly choose 50/50 — Single choice ("multiple": false, one correct answer per question) or Multiple choice ("multiple": true, 1–3 correct answers per question).

Output format: Start with a brief intro sentence, then output a quiz block using EXACTLY this format:

[quiz:{{"title":"<quiz title>","multiple":<true|false>,"questions":[{{"q":"<question text>","options":["<option 1>","<option 2>","<option 3>","<option 4>"],"correct":[<index>],"explanation":"<why correct>"}}]}}]

Rules:
- Generate exactly {num_questions} questions based on the content. If the user explicitly asked for a specific number of questions, honour that number exactly.
- The top-level "multiple" field MUST be present: true for multiple choice, false for single choice
- Each question has 3-4 options
- For single choice ("multiple": false): "correct" must contain exactly ONE index
- For multiple choice ("multiple": true): "correct" contains 1-3 indices (never 0, never 4 or more)
- Include a brief explanation for each correct answer
- Questions should test understanding, not just recall
- CRITICAL: NEVER include [source:N], [source:1], [source:2] or any source citations anywhere in the quiz JSON. No citations in questions, options, explanations, or title. Source references break the JSON rendering and must be completely omitted from the entire [quiz:...] block.
- The quiz JSON must be valid JSON on a single line after [quiz:
- Write the quiz in the same language as the retrieved context
- Never use em dash (—) or en dash (–). Use a regular hyphen (-) instead.
- Before the [quiz:...] block, write 1-2 intro sentences about the quiz topic. Explicitly mention whether this is a single choice quiz (one correct answer per question) or a multiple choice quiz (one or more correct answers per question). If the user explicitly requested a quiz type, acknowledge it (e.g. "As you requested, this is a multiple choice quiz…").
- CRITICAL — ANSWER POSITION RANDOMIZATION: Shuffle option order for every question so correct answers land unpredictably. Specifically: (1) Never put the wrong option(s) always at the same index — wrong answers must be spread across all positions. (2) The correct index set must vary per question; do NOT let index 2 (3rd position) be the wrong outlier on most questions. (3) Across all {num_questions} questions each available position (0,1,2 and 3 when 4 options) should appear as a correct answer roughly equally. (4) For multiple choice, vary the count of correct answers across questions — use 1 correct on some, 2 on others, 3 on others; never repeat the same count on every question.

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

    Number of questions to generate: {num_questions}

    Question:
    {question}

    Retrieved context (most relevant chunks):
    {context}""",
        ),
    ]
)

__all__ = ["QUIZ_PROMPT"]

