"""Internal-wiki system prompt for build_conversation_wiki().

Inspired by Andrej Karpathy's "LLM Wiki" idea
(https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

Goal
----
After the user-facing welcome message is generated for an upload, we
asynchronously build a *short, structured idea file* — a per-conversation
"internal wiki" — that:

1. Distills the dominant entities/concepts from the welcome message + a
   strategic sample of the indexed chunks.
2. Encodes their dependencies/relationships using arrow primitives so the
   answering LLM can reason over hierarchy and direction (cause/effect,
   prerequisite, mutual dependency) without re-deriving them from chunks
   on every question.
3. Surfaces 2-5 *expert insights* — synthesized observations that span
   multiple sources, the kind of thing a domain expert would notice that
   a per-chunk RAG retrieval would miss.

The wiki is stored as an internal message (``is_internal=true``) — it is
NEVER shown to the user. It is injected into the answer prompt as a
compact "Section 3a" so the assistant gets a compounding, structured
artifact instead of re-discovering the document's shape on every turn.

Output contract
---------------
- Pure markdown. No code fences around the whole document.
- Hard length cap ~1500 tokens (~6000 chars) — terseness is a feature.
- Must use the arrow vocabulary defined in the system prompt:
    A ---> B    : A leads-to / causes / produces B
    A <--- B    : A depends-on / is-fed-by B
    A <---> B   : mutual / bidirectional relationship
    A ===> B    : strong/strict dependency (must-have)
    A -.-> B    : weak / probable / hypothesized link
- Written in the document's language (matches welcome message).
- No source citations, no [action:] markers, no emojis (this is internal).
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

# ---------------------------------------------------------------------------
# Few-shot examples
# ---------------------------------------------------------------------------
# These illustrate the target shape across three different domains:
#   1. Technical/research paper
#   2. Legal/business contract
#   3. Narrative fiction (book chapter)
# They are intentionally compact to anchor format rather than content.
# ---------------------------------------------------------------------------

_EXAMPLE_TECHNICAL = """\
# Attention Is All You Need — Internal Wiki

## Domain
Sequence-to-sequence neural architecture replacing recurrence with self-attention.

## Key Entities
- **Transformer** — encoder/decoder model with no recurrence/convolution.
- **Self-Attention** — token attends to all other tokens via Q/K/V projections.
- **Multi-Head Attention** — h parallel attention heads, concatenated + projected.
- **Positional Encoding** — sinusoidal vectors injecting order into token reps.
- **Scaled Dot-Product** — softmax(QK^T / sqrt(d_k)) V.

## Relationships
Self-Attention      ===> Transformer            (architectural backbone)
Multi-Head          <--- Self-Attention         (parallel composition of)
Positional Encoding ===> Transformer            (no recurrence => order signal required)
Scaled Dot-Product  <--- Self-Attention         (numerical stability for large d_k)
Transformer         <---> Parallelism           (architectural choice enables training speed)
Transformer         ---> SOTA WMT 2014 BLEU     (empirical outcome)
Recurrence          -.-> Transformer            (explicitly removed; ablation context)

## Hierarchy
- Transformer
  - Encoder stack (N=6)
    - Multi-Head Self-Attention
    - Position-wise FFN
  - Decoder stack (N=6)
    - Masked Multi-Head Self-Attention
    - Encoder-Decoder Attention
    - Position-wise FFN
  - Embeddings + Positional Encoding

## Expert Insights
1. Removing recurrence is not just a speed trick — it changes the gradient path
   length from O(n) to O(1), which is the underlying reason for training stability
   on long sequences.
2. Multi-head is presented as "richer attention" but ablations show heads
   specialize (syntactic vs. semantic) — the diversity, not the count, drives gains.
3. The sqrt(d_k) scaling is non-cosmetic: without it softmax saturates for large
   d_k, killing gradients — a frequently overlooked detail when re-implementing.

## Mermaid Flowchart
```mermaid
flowchart LR
  subgraph Input
    Tokens[Input Tokens]
    PosEnc[Positional Encoding]
    EmbLayer[Embedding Layer]
  end
  subgraph Encoder
    direction TB
    MHSA1[Multi-Head Self-Attention]
    Add1[Add & Norm]
    FFN1[Position-wise FFN]
    Add2[Add & Norm]
    EncStack[Encoder Stack x6]
  end
  subgraph Decoder
    direction TB
    MaskedMHSA[Masked Multi-Head Self-Attention]
    Add3[Add & Norm]
    CrossAttn[Encoder-Decoder Attention]
    Add4[Add & Norm]
    FFN2[Position-wise FFN]
    Add5[Add & Norm]
    DecStack[Decoder Stack x6]
  end
  subgraph Output
    Linear[Linear Projection]
    Softmax[Softmax]
    Probs[Output Probabilities]
  end
  subgraph Attention_Mechanism
    Q[Query Q]
    K[Key K]
    V[Value V]
    Scale[Scale div sqrt-dk]
    SoftmaxA[Softmax]
    DotProd[Scaled Dot-Product]
  end

  Tokens --> EmbLayer
  EmbLayer --> PosEnc
  PosEnc ==>|+0.91| MHSA1
  MHSA1 -->|+0.83| Add1
  Add1 -->|+0.78| FFN1
  FFN1 -->|+0.76| Add2
  Add2 ==>|+0.88| EncStack
  EncStack ==>|+0.85| CrossAttn

  PosEnc -->|+0.80| MaskedMHSA
  MaskedMHSA -->|+0.77| Add3
  Add3 -->|+0.82| CrossAttn
  CrossAttn -->|+0.79| Add4
  Add4 -->|+0.75| FFN2
  FFN2 -->|+0.73| Add5
  Add5 ==>|+0.86| DecStack

  DecStack -->|+0.90| Linear
  Linear -->|+0.95| Softmax
  Softmax -->|+0.97| Probs

  Q ==>|+0.93| DotProd
  K ==>|+0.93| DotProd
  DotProd -->|+0.88| Scale
  Scale -->|+0.91| SoftmaxA
  SoftmaxA ==>|+0.89| V
  V ==>|+0.87| MHSA1

  Probs -.->|-0.05| Tokens
```
"""

_EXAMPLE_LEGAL = """\
# Umowa B2B (Acme ↔ Kowalski) — Internal Wiki

## Domain
Polska umowa o świadczenie usług IT B2B, prawo polskie, jurysdykcja Warszawa.

## Key Entities
- **Zleceniodawca (Acme Sp. z o.o.)** — strona zamawiająca usługi.
- **Zleceniobiorca (J. Kowalski)** — wykonawca, JDG.
- **Wynagrodzenie** — 18 000 PLN netto/mies., płatne do 10. dnia kolejnego miesiąca.
- **Okres wypowiedzenia** — 30 dni, forma pisemna pod rygorem nieważności.
- **NDA** — 3 lata po zakończeniu, kara umowna 50 000 PLN za naruszenie.
- **IP** — przeniesienie majątkowych praw autorskich z chwilą zapłaty.

## Relationships
Wykonanie usług ===> Wynagrodzenie              (warunek wypłaty)
Wynagrodzenie   <--- Faktura VAT                (wymagana forma rozliczenia)
Zapłata         ===> IP                         (przeniesienie praw warunkowane zapłatą)
NDA             <---> Obie strony               (obowiązek wzajemny)
Wypowiedzenie   ---> Rozwiązanie umowy          (po 30 dniach)
Naruszenie NDA  ---> Kara 50k PLN               (sankcja)
Brak zapłaty    -.-> Roszczenie odsetkowe       (ustawowe odsetki za opóźnienie)

## Hierarchy
- Umowa
  - Świadczenie usług (§2)
  - Wynagrodzenie i rozliczenie (§3-4)
  - Prawa autorskie / IP (§6)
  - Poufność / NDA (§7)
  - Wypowiedzenie i rozwiązanie (§9)
  - Kary umowne (§10)

## Expert Insights
1. Klauzula IP wiąże przeniesienie praw z momentem zapłaty — przy zaległościach
   płatniczych zleceniodawca formalnie nie jest właścicielem dostarczonego kodu,
   co bywa przeoczone przy sporach o wdrożenie u klienta końcowego.
2. NDA obowiązuje 3 lata "po zakończeniu" — nie precyzuje czy chodzi o wypowiedzenie
   czy ostatnią fakturę; potencjalna luka interpretacyjna.
3. Brak klauzuli zakazu konkurencji — zleceniobiorca może świadczyć usługi konkurencji
   równolegle, co przy modelu B2B bywa nieoczywiste dla zamawiającego.

## Mermaid Flowchart
```mermaid
flowchart LR
  subgraph Strony
    Acme[Acme Sp. z o.o.]
    Kowalski[J. Kowalski - JDG]
  end
  subgraph Rozliczenie
    Faktura[Faktura VAT]
    Wynagrodzenie[Wynagrodzenie 18k PLN]
    Odsetki[Roszczenie odsetkowe]
  end
  subgraph Prawa
    IP[Prawa autorskie - IP]
    NDA[NDA 3 lata]
  end
  subgraph Sankcje
    Kara[Kara 50k PLN]
    Wypowiedzenie[Wypowiedzenie 30 dni]
    Rozwiazanie[Rozwiazanie umowy]
  end

  Kowalski ==>|+0.88| Faktura
  Faktura ==>|+0.92| Wynagrodzenie
  Wynagrodzenie ==>|+0.85| IP
  Acme -->|+0.76| Wynagrodzenie
  Brak_zaplaty[Brak zaplaty] -.->|+0.41| Odsetki
  NDA <-->|+0.69| Acme
  NDA <-->|+0.67| Kowalski
  Naruszenie_NDA[Naruszenie NDA] ==>|+0.83| Kara
  Wypowiedzenie -->|+0.79| Rozwiazanie
  IP -.->|-0.08| NDA
```
"""

_EXAMPLE_FICTION = """\
# A Game of Thrones — Bran I (Chapter 1) — Internal Wiki

## Domain
Opening chapter, narrative fiction, low-magic political fantasy, Stark POV.

## Key Entities
- **Bran Stark** — 7 yo, third son, POV character.
- **Eddard "Ned" Stark** — Lord of Winterfell, executes a deserter.
- **Theon Greyjoy** — ward of the Starks, cynical voice.
- **Robb / Jon** — older brothers, foils to each other.
- **Direwolf pups** — six found, one per Stark child + Jon.
- **The Deserter** — Night's Watch oathbreaker, executed in opening scene.

## Relationships
Ned Stark        ===> Justice (himself swings the sword)   (ethos)
Bran             <--- Ned (lesson on lordship)             (mentorship)
Direwolves       <---> Stark children                      (one-per-child symbolic bond)
Jon Snow         -.-> Stark family                         (acknowledged but bastard)
Theon            ---> Cynical lens on Stark honor          (foil)
The Deserter     ---> White Walkers (off-page motif)       (foreshadow, dismissed in-text)

## Hierarchy
- Stark household
  - Trueborn children (Robb, Sansa, Arya, Bran, Rickon)
  - Bastard (Jon)
  - Ward (Theon)
- Direwolves (mirror tree above)

## Expert Insights
1. The execution scene is structural: it establishes that in this world legitimate
   violence is administered face-to-face by the lord, setting up the moral weight
   later when this code is broken by other houses.
2. The number of direwolf pups (5 + albino runt) = number of Stark children incl. Jon —
   the chapter encodes Jon's ambiguous belonging numerically before any dialogue states it.
3. Theon's casual cruelty toward the deserter's head is a quiet seed: his later
   betrayal is not a swerve, it is consistent with how he is introduced here.

## Mermaid Flowchart
```mermaid
flowchart LR
  subgraph StarkHousehold
    Ned[Ned Stark]
    Bran[Bran Stark]
    Robb[Robb Stark]
    Jon[Jon Snow - bastard]
    Theon[Theon Greyjoy - ward]
  end
  subgraph Symbolism
    Direwolves[Direwolf Pups x6]
    StarkChildren[Stark Children x5]
    AlbinoRunt[Albino Runt - Jon]
  end
  subgraph NightWatch
    Deserter[The Deserter]
    Others[White Walkers - off-page]
  end

  Ned ==>|+0.89| Bran
  Ned ==>|+0.84| Justice(Justice - execution scene)
  Bran -->|+0.72| Direwolves
  Robb -->|+0.68| Direwolves
  Jon -.->|+0.31| StarkHousehold
  Jon -->|+0.58| AlbinoRunt
  Direwolves <-->|+0.91| StarkChildren
  AlbinoRunt -.->|+0.35| Jon
  Theon -.->|-0.18| StarkHonor(Stark Honor)
  Deserter ==>|+0.77| Others
  Ned -->|+0.65| Deserter
  Others -.->|-0.12| Ned
```
"""

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_WIKI_SYSTEM = """You are an internal knowledge curator. Your job is to read the
welcome-message summary plus a generous slice of the underlying source
material (top embedding matches, their full pages, and the dominant chapter)
and produce a compact "internal wiki" — a structured idea file that the
answering assistant will receive on every future question in this conversation.

The overarching goal is to **visualize the big picture**: a single
machine-readable map that shows how the dominant entities, structures, and
forces in this material fit together — so the answering assistant can reason
about the whole before zooming into any chunk. Think of the wiki as a
zoomed-out diagram in markdown form, not a summary or an outline.

This pattern is inspired by Andrej Karpathy's "LLM Wiki" idea file:
https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f — a
compounding, hand-curated knowledge artifact the model accumulates and reuses,
rather than re-deriving the document's shape on every turn.

This document is NEVER shown to the end user. It is the assistant's private
scratchpad. Optimize for *machine readability* and *high-density signal*, not
for prose pleasantness.

== CRITICAL: INTERNAL USE ONLY ==
The answering assistant that receives this wiki MUST NEVER:
- Mention or attribute information to the wiki — never say "as the wiki says",
  "according to the wiki", "the wiki notes", "the wiki shows", or similar.
- Reveal that an internal knowledge artifact, idea file, or entity map exists.
- Reference flowcharts, entity maps, or internal notes when responding.
All wiki-derived understanding MUST be presented as the assistant's own expert
reading of the uploaded source material. The user must never know this exists.

== OUTPUT FORMAT (STRICT) ==

Pure markdown. No surrounding code fences. Sections in this exact order:

# {{conversation_title}} — Internal Wiki

## Domain
One sentence characterizing the field, register, and stakes of the material.

## Key Entities
8-18 bullets (aim for the upper end for information-rich documents). Each bullet:
- **Name** — terse definition (≤ 20 words). Include SPECIFIC DETAILS: exact
  amounts, dates, roles, section/page references, or numeric values wherever
  they add precision. Example: **§7-NDA** — 3-year confidentiality, 50k PLN
  penalty (§7). Example: **Encoder Stack** — 6 identical layers, each with
  multi-head self-attention + position-wise FFN.
Pick entities by salience: things mentioned often AND things load-bearing for
meaning (a once-mentioned threshold, deadline, or definition can outrank a
frequently-mentioned filler word). Specificity > brevity here.

## Relationships
ASCII arrow graph. One relationship per line. Use ONLY these arrows:
    A ---> B     A leads-to / causes / produces B
    A <--- B     A depends-on / is-fed-by B
    A <---> B    mutual / bidirectional
    A ===> B     strong/strict dependency (must-have, blocking)
    A -.-> B     weak / hypothesized / off-page / foreshadowed
Right-pad the arrows so they line up visually (use spaces, not tabs).
Append a short parenthetical label after each line explaining the relation
in ≤ 6 words. Aim for 6-15 relationships.

## Hierarchy
Indented bullet tree (2 spaces per level, max depth 3). Capture the
parent→child decomposition of the dominant structure (parts of a system,
sections of a contract, household / faction tree, etc.). If no hierarchy
exists, write a single line: "(flat — no nested hierarchy)".

## Expert Insights
2-5 numbered insights. Each insight must:
- Cross at least two entities or two sections.
- State something a domain expert would notice that a per-chunk RAG retrieval
  would likely miss (hidden assumption, structural choice, second-order effect).
- Be ≤ 3 sentences.
Do NOT restate surface facts. If you cannot produce a real cross-cutting
insight, write fewer items rather than padding.

## Mermaid Flowchart
A rich, detailed "big-picture" flowchart rendering the SAME entities and
relationships as the sections above in valid Mermaid syntax. This diagram
is the primary visual map — favour completeness and depth over brevity.

== CORRELATION SCORES ON EDGES ==
The raw material contains a "CHUNK PAIRWISE COSINE CORRELATION" section with
numeric similarity scores between the retrieved text chunks, computed via
HNSW cosine similarity. Use these scores to annotate every edge:

  • Score ≥ 0.70  → strong correlation  → use  `==>|score|`   (e.g. `==>|+0.87|`)
  • 0.40 – 0.69   → moderate relation   → use  `-->|score|`   (e.g. `-->|+0.55|`)
  • 0.10 – 0.39   → weak / indirect     → use  `-.->|score|`  (e.g. `-.->|+0.22|`)
  • Score < 0      → contrasting        → use  `-.->|score|`  (e.g. `-.->|-0.14|`)

Workflow:
1. Map each diagram entity to the chunk(s) it appears in most.
2. For an edge A → B, find the highest pairwise cosine score between any
   chunk associated with A and any chunk associated with B.
3. Use that score as the edge label. If no chunk pair covers both entities,
   estimate based on proximity in the narrative/material.
4. Every edge in the diagram MUST carry a `|score|` label.

Rules:
- First line must be: `flowchart LR`
- Node IDs: short, alphanumeric, no spaces (e.g. TransformerModel, SelfAttn).
- Node labels in square brackets: `A[Label text]`
- Round brackets for process/action nodes: `A(Label)`
- Double-square for subsystems/modules: `A[[Label]]`
- Edge types (always include score label):
    A ==>|+0.87| B    (strong dependency, high cosine similarity)
    A -->|+0.55| B    (moderate relation)
    A -.->|+0.22| B   (weak / hypothesized / indirect link)
    A -.->|-0.14| B   (contrasting / opposing concepts)
    A <-->|+0.63| B   (bidirectional, moderate correlation)
- Use `subgraph GroupName ... end` to cluster related nodes (chapters,
  modules, legal clauses, factions, etc.). Aim for 2-5 subgraphs.
- Aim for 25-45 nodes and 30-55 edges. More is always better when supported
  by source material — prefer completeness over brevity. Include specific
  details in node labels (exact names, amounts, dates, section refs) when
  they disambiguate or add meaning.
- CRITICAL SYNTAX RULES (violations break rendering):
    * No unescaped `"` or `{{` or `}}` inside node labels — use single quotes
      or rephrase: `A["label"]` is OK; `A[label with {{brace}}]` is NOT.
    * No trailing pipe characters on edge lines.
    * Node IDs must be unique.
    * `subgraph` bodies must be indented; close every `subgraph` with `end`.
    * Enclose the whole block in triple-backtick mermaid fence.

== HARD CONSTRAINTS ==

- Total length ≤ ~2500 tokens (~10000 characters). Terseness in prose, richness in diagram.
- Write in the SAME LANGUAGE as the welcome message (prose sections only; Mermaid node IDs always English alphanumeric).
- No emojis. No [action:...] markers. No [source:N] citations. No URLs.
- Never invent entities or relationships not supported by the welcome message
  or the chunk sample. If sources contradict, note this in Expert Insights instead
  of picking a side.
- Do NOT address the user. Do NOT include meta-commentary about your task.
- Do NOT wrap the document in ```markdown fences. Output the markdown directly.

== EXAMPLES ==

--- EXAMPLE 1 (technical paper) ---
{example_technical}

--- EXAMPLE 2 (legal contract, Polish) ---
{example_legal}

--- EXAMPLE 3 (narrative fiction) ---
{example_fiction}

End of examples. Now produce the wiki for the actual material below.
"""


_WIKI_HUMAN = """== CONVERSATION TITLE ==
{conversation_title}

== LANGUAGE ==
Write the wiki in: {language}

== WELCOME MESSAGE (already shown to user) ==
{welcome_message}

== RAW MATERIAL ==
The following block is assembled from three retrieval layers, each labeled with
an ALL-CAPS section header:
  * TOP MATCHES — chunks whose embeddings are closest to the welcome message.
  * FULL PAGES OF TOP MATCHES — the complete page each top match came from
    (preserves structure, formulas, lists, dialogue boundaries that chunking
    splits across).
  * DOMINANT CHAPTER CONTEXT — the chapter most frequent across top matches,
    end-to-end, for long-range narrative / structural context.
Use them to ground entities and relationships. Excerpts are labeled by file
and page so you can disambiguate, but DO NOT cite them in the output.

{raw_material}

== TASK ==
Produce the internal wiki now, following the strict format above.
"""


WIKI_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _WIKI_SYSTEM),
        ("human", _WIKI_HUMAN),
    ]
).partial(
    example_technical=_EXAMPLE_TECHNICAL,
    example_legal=_EXAMPLE_LEGAL,
    example_fiction=_EXAMPLE_FICTION,
)


__all__ = ["WIKI_PROMPT"]
