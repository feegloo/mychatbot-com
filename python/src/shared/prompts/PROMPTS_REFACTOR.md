# Prompts refactor (step 2) — plan

This folder will become the single source of truth for every system prompt the
Python RAG engine uses. Step 1 (notebook removal, README rewrite) is done.
Step 2 is to move prompts here and rebuild them from shared building blocks.

## User spec (verbatim)

> 1. welcome message + [action] as 1 prompt — knowledge about generating [label]
>    and [action] should be EXACTLY the same both for welcome message and
>    assistant answer, so shared logic could be in 1 file
>    `labels_actions_prompt.ts` / `assistant_shared_prompt.py`.
> 2. standard assistant message as exactly 1 prompt with shared rules.
> 3. edge case "empty book" like Mathnawi (600-page Arabic OCR PDF) with a fast
>    welcome from full-PDF text + OCR-in-progress messaging + post-OCR regen
>    using the standard welcome prompt, prefixed
>    "UPDATE: after parsing all N/N pages: …".
>
> Source budget: welcome up to 3 (typically 1–2), assistant up to 10 (typically 4–6).

## Target files

| File | Owns |
|---|---|
| `voice_tone.py` | VOICE & IDENTITY, author-style mimicry, creativity band [0.2–0.6], common-knowledge signaling (EN+PL), name-drop specifics |
| `response_formats.py` | `[poem]...[/poem]`, chapter en-dash dialogue, `[c:color]` palette (10 colors), emoji palette, KaTeX, markdown tables, citation `[source:N]` frequency (welcome ≤3 / assistant ≤10), page/chapter natural references (EN+PL) |
| `labels_actions.py` | **Shared** `[action:Label]` rules: 7 buttons (1–2 plain, 3 visible rich, 4–7 More…), language mirroring (rule #1), image-gen 50/50 placement with mandatory "inspired" keyword, creative-writing/wisdom-quote/factual-docs rules, branches-not-sequels, anti-repetition, brevity (3–5 words per label) |
| `welcome.py` | Standard welcome system prompt, composed from the three shared modules above + welcome-specific goal |
| `welcome_empty_book.py` | Edge-case: near-empty PDF, OCR in progress, EXIF-based expert preview, explicit "I'll update this after parsing all N pages" |
| `assistant.py` | RAG answer prompt, composed from shared modules + sections (question / matching sources / chat history / previous suggestions) |
| `quiz.py` | Existing `QUIZ_PROMPT` from `rag.py`, moved unchanged |

## Migration order

1. Extract `labels_actions.py` (it's referenced by both welcome and assistant — highest leverage).
2. Extract `voice_tone.py`, `response_formats.py`.
3. Compose `welcome.py` and `welcome_empty_book.py`; wire through `describe.py` and `suggested_questions.py`.
4. Compose `assistant.py`; wire `rag.py` to use it.
5. Move `quiz.py`; wire `rag.py`.
6. Delete inline prompts from `rag.py`, `suggested_questions.py`, `describe.py`.
7. Verify public API of `answer_question`, `describe_documents`, `suggest_questions_from_chunks` is unchanged.
8. Run `python -m pytest`, `ruff check .`, `ruff format --check .`.

## Invariants (must be preserved)

- Bilingual EN + PL content.
- 7-action-button rule, language-mirroring rule #1.
- `[source:N]` citation budgets: welcome 1–3 (typ. 1–2), assistant 4–6 (max 10).
- Temperature self-regulation band [0.2, 0.6] with default 0.4 and 10-seed rotation (seeds live in `rag.py`, prompts only describe behavior).
- Image-gen "inspired" keyword mandatory.
- Empty-book edge case: fast welcome ASAP, later regenerated with standard prompt + "UPDATE: after parsing all N/N pages:" prefix; emitted via `welcome_message` SSE with `regenerated: true`.
