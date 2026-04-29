"""C4 diagram prompt for build_welcome_c4().

Generates a Mermaid C4Context diagram from the welcome message text alone —
no chunks needed. This is intentionally fast and lightweight compared to the
wiki builder: the welcome message already summarises all dominant entities,
so asking the LLM to model them as a C4 context diagram is a single-pass call.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

_SYSTEM = """\
You are a visual knowledge architect. Given a document summary (the "welcome
message" shown to a user after uploading a file), produce a single valid
Mermaid C4Context diagram that maps the key actors, systems, and relationships
described in the document.

== OUTPUT FORMAT ==
Output ONLY the triple-backtick mermaid fence — nothing else, no prose, no
explanation, no surrounding markdown.

The diagram must start with:
```mermaid
C4Context
  title <Short descriptive title — ≤ 8 words>
```

Rules:
- Use `Person(alias, "Label", "Description")` for human actors, users, or roles.
- Use `System(alias, "Label", "Description")` for the main system or subject.
- Use `System_Ext(alias, "Label", "Description")` for external systems, tools,
  or third-party services.
- Use `Boundary(alias, "Label")` to group related nodes when it adds clarity.
- Use `Rel(from, to, "label")` for directed relationships.
- Use `BiRel(from, to, "label")` for bidirectional relationships.
- Alias identifiers: short camelCase, alphanumeric only, e.g. `mainSys`, `adminUser`.
- Aim for 4–10 nodes and 3–8 relationships.
- Keep labels and descriptions concise: labels ≤ 5 words, descriptions ≤ 10 words.
- Output node labels in the language of the welcome message.

CRITICAL: Enclose the diagram in a ```mermaid ... ``` fence and output NOTHING
outside that fence.
"""

_HUMAN = """\
== WELCOME MESSAGE ==
{welcome_message}

== TASK ==
Produce the C4Context diagram now.
"""

C4_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _SYSTEM),
        ("human", _HUMAN),
    ]
)

__all__ = ["C4_PROMPT"]
