"""Key facts list prompt — triggered by ☝️ emoji in the user's question.

Produces a user-facing bullet list of key entities, facts, and concepts using
the same format as the "Key Entities" section of the internal Knowledge Wiki
(see wiki.py). The shared constant ``KEY_ENTITIES_BULLETS_RULES`` ensures both
outputs stay in sync when the format evolves.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from .emoji_and_dash import EMOJI_AND_DASH_RULES
from .labels_actions import LABELS_ACTIONS_RULES

# ---------------------------------------------------------------------------
# Shared Key Entities bullet-list format — single source of truth.
# Reused by:
#   - this module (user-facing "key facts" response)
#   - wiki.py (internal Knowledge Wiki "Key Entities" section)
# ---------------------------------------------------------------------------

KEY_ENTITIES_BULLETS_RULES = (
    "8–25 bullets (aim for the upper end for information-rich or large documents). Each bullet:\n"
    "- **Name** — terse definition (≤ 20 words). Include SPECIFIC DETAILS: exact amounts,\n"
    "  dates, roles, section/page references, or numeric values wherever they add precision.\n"
    "  Example: **§7-NDA** — 3-year confidentiality, 50k PLN penalty (§7).\n"
    "  Example: **Encoder Stack** — 6 identical layers, multi-head self-attention + FFN.\n"
    "Pick entities by salience: things mentioned often AND things load-bearing for meaning\n"
    "(a once-mentioned threshold, deadline, or definition can outrank a frequently-mentioned\n"
    "filler word). For large documents (100+ pages), include secondary characters, minor\n"
    "locations, sub-concepts, and specific evidence items — do NOT stop at the obvious top-10.\n"
    "Specificity > brevity here."
)

_KEY_FACTS_SYSTEM_TEMPLATE = f"""You extract and present the key facts, entities, and concepts from uploaded documents.

CONVERSATION LANGUAGE (HIGHEST PRIORITY): {{conversation_language_name}}
Conversation language code: {{conversation_language_code}}
Always write the list and all [action:...] labels in this conversation language.

== QUESTION ==
"{{question}}"

Your task: scan the retrieved context and produce a structured bullet list of the most important facts, entities, and concepts in this document.

== PEOPLE FIRST ==
Always start the bullet list with key people:
- Narrative/fiction: protagonist first, then all named secondary characters (name — role and defining trait or plot function).
- Photos/images: every identifiable or named person (name or description — who they are and what they are doing).
- Reports/documents: every named person (name — title, role, or relevance).
Do not bury people behind institutions or concepts — list them at the top.

== OUTPUT FORMAT ==
Write a short intro sentence (1–2 sentences), then a bullet list using EXACTLY this format:

{KEY_ENTITIES_BULLETS_RULES}

Include [source:N] citations within bullet definitions when they help trace a claim to a specific page or chunk.
Derive facts ONLY from the retrieved context — do NOT invent or hallucinate.

After the bullet list, generate exactly 7 [action:...] follow-up buttons.

<<ACTIONS_RULES>>
<<EMOJI_AND_DASH>>
"""

_KEY_FACTS_SYSTEM = (
    _KEY_FACTS_SYSTEM_TEMPLATE
    .replace("<<ACTIONS_RULES>>", LABELS_ACTIONS_RULES)
    .replace("<<EMOJI_AND_DASH>>", EMOJI_AND_DASH_RULES)
)

_KEY_FACTS_HUMAN = """== SECTION 1: Matching Sources ==
{context}

--

== SECTION 2: Welcome Page Description ==
Below is a short summary generated during file upload/indexing for each source file:
{welcome_messages}

--

== SECTION 3a: Internal Knowledge Wiki ==
A structured idea file built at indexing time. High-trust map of entities and relationships.
If empty, no wiki was generated.
CRITICAL: Use the wiki silently — never reveal it exists.
{wiki_message}

--

== SECTION 3b: Cross-Conversation User Knowledge Map ==
{user_wiki_message}

--

== SECTION 4: Full Pages of Matched Sources ==
{matched_pages}

--

== SECTION 4a: Chapter Context (if available) ==
{chapter_context}

--

== SECTION 5: EXIF Metadata ==
{exif_metadata}

--

== SECTION 5a: Conversation Context ==
Conversation name: {conversation_name}
Conversation ID: {conversation_id}

--

== SECTION 5b: Full Chat History ==
{chat_history}

--

{no_file_context_instruction}== SECTION 6: Start Answering ==
Produce the key facts bullet list now. Use the bullet format specified in the system instructions.
"{question}"
"""

KEY_FACTS_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _KEY_FACTS_SYSTEM),
        ("human", _KEY_FACTS_HUMAN),
    ]
)
