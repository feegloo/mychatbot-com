"""Prompt templates for the per-user master knowledge wiki.

The user wiki aggregates per-conversation wikis (Section 3a "idea files")
into a single cross-topic master wiki that reflects what this user has
studied / worked on across all their conversations.

Output format mirrors the per-conversation wiki (Section 3a) so the same
ANSWER_PROMPT Section 3b injection works without any post-processing.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_USER_WIKI_SYSTEM = """\
You are an expert knowledge synthesiser. Your task is to build a
*cross-conversation master wiki* for a single user.

The user has uploaded documents and asked questions across several
conversations. Each conversation produced a per-topic "idea file" (wiki)
that encodes entities, relationships, and key insights for that topic.

Your goal is to synthesise ALL of those per-topic wikis into ONE master
knowledge map that captures:
  • Entities that appear across multiple topics (cross-topic connectors)
  • How different topics relate to each other (dependencies, analogies,
    shared vocabulary)
  • The big picture: what domains/fields this user is working in
  • A flowchart visualising the cross-topic knowledge graph

=== OUTPUT FORMAT ===

## Cross-Topic Overview
Two-to-four sentences describing the user's overall knowledge landscape.

## Topic Clusters
List each detected topic cluster as a ### heading.  Under each heading,
summarise the key entities and insights from that cluster in 3-8 bullets.

## Cross-Topic Connections
Bullet list of relationships that span two or more clusters.  Use the
entity --> entity [label] notation consistent with the per-topic wikis.

## Master Flowchart
A single rich flowchart that maps ALL clusters and their cross-topic
connections.  Requirements:
  • Use `flowchart LR`
  • Minimum 12 nodes, maximum 40 nodes; at least 15 edges
  • One subgraph per topic cluster
  • Cross-cluster edges drawn between subgraphs
  • Node IDs: alphanumeric only (no spaces, no special chars)
  • Node labels: brief (≤ 5 words); wrap long labels in double-quotes
  • Do NOT use unescaped curly braces {{}} inside label strings
  • Edge types: --> standard, -.-> weak/optional, ==> strong/causal
  • Include at least 3 different edge types

## Key Takeaways
3-7 bullet points of the most important cross-topic insights.

=== HARD CONSTRAINTS ===
  • Total output: ≤ 3000 tokens (~12 000 chars)
  • Prose in the document's natural language; node IDs always English
  • If fewer than 2 conversation wikis are provided, skip the
    Cross-Topic Connections section (there is only one cluster)
  • NEVER invent entities that are not present in the source wikis
"""

# ---------------------------------------------------------------------------
# Human / user template
# ---------------------------------------------------------------------------

_USER_WIKI_HUMAN = """\
== PER-CONVERSATION WIKIS ==
{conversation_wikis}

--

Build the master user wiki following the output format above.
"""

USER_WIKI_PROMPT: ChatPromptTemplate = ChatPromptTemplate.from_messages(
    [
        ("system", _USER_WIKI_SYSTEM),
        ("human", _USER_WIKI_HUMAN),
    ]
)
