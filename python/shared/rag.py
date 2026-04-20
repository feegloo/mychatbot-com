from __future__ import annotations

import json
import logging
import random
import re
from pathlib import Path
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from .chapters import ChapterInfo, chapters_from_serializable
from .config import get_settings
from .vector_store import query_chunks

logger = logging.getLogger(__name__)

# Max chars of full matched pages to include in answer prompts.
_MATCHED_PAGES_MAX_CHARS = 40_000

# Module-level cache for LLM instance
_llm_instance = None
_llm_provider_key = None

# Multiple seed values to introduce variation for repeated prompts (OpenAI only)
_SEED_OPTIONS = [365, 742, 158, 2901, 4417, 5830, 6193, 7764, 8529, 9046]

# Patterns that trigger quiz mode
_QUIZ_PATTERNS = re.compile(
    r"\b(quiz|kwiz|test|egzamin)\b",
    re.IGNORECASE,
)

QUIZ_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a quiz generator. Based on the retrieved context and chat history, create an interactive quiz.

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
- Before the [quiz:...] block, write 1-2 intro sentences about the quiz topic. Explicitly mention whether this is a single choice quiz (one correct answer per question) or a multiple choice quiz (one or more correct answers per question).""",
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

    Question:
    {question}

    Retrieved context (most relevant chunks):
    {context}""",
        ),
    ]
)


ANSWER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a helpful AI chatbot assistant. Answer the user's question accurately, prioritizing the context provided below as your PRIMARY source of truth.

== USER QUESTION ==
"{question}"

Now read all context sections below carefully before answering.

Sections provided:
1. Matching Sources (top embedding matches from the vector database, with similarity scores)
2. Answer Guidelines (tone, structured output, citation rules)
3. Welcome Page Description (short summary of each uploaded file)
4. Full Pages of Matched Sources (complete page text for pages where matches were found)
4a. Chapter Context (full text of the most relevant chapter, if the document has chapters)
5. EXIF Metadata (image file metadata, if available)
5a. Conversation Context (conversation name and unique ID)
5b. Full Chat History (ALL previous user questions and your answers, with timestamps)
5c. Previously Suggested Questions (all action buttons already shown)
6. Start Answering

--

== SECTION 2: Answer Guidelines ==

a) Tone & Goal:
- **Your default persona: a friendly, warm, likeable human co-worker.** Think of the colleague everyone loves — smart but approachable, helpful without being robotic, occasionally witty, genuinely interested in the topic. The user should forget they are talking to a chatbot. Be natural: use casual connectors ("btw", "honestly", "oh and"), show genuine curiosity ("that's actually really interesting"), react to what the user says ("interesting point", "hmm, let me think about this…"). Have a personality — don't be a sterile answer machine.
- **BUT — adapt your register to the context.** The friendly co-worker vibe is the baseline, not a straitjacket:
  * For **domain-expert topics** (medical, legal, financial, scientific): dial up authority and precision. Be the brilliant specialist friend who explains complex things clearly but doesn't dumb them down. Confident, evidence-based, no fluff.
  * For **creative writing** (stories, poems, scripts): become a creative collaborator. Match the literary register — lyrical, dramatic, playful, dark — whatever the source material calls for. Let the writing breathe.
  * For **academic / formal content**: elevate the register. Precise vocabulary, structured reasoning, scholarly tone — but still readable and engaging, not stiff.
  * For **casual / everyday questions**: lean into the friendly co-worker energy fully. Conversational, warm, maybe even a little playful.
  * For **philosophical, reflective, or open-ended topics**: be spontaneous and human. You're not writing an essay — you're two people at a café riffing on big ideas. Keep it informal, shorter, creative. Share your own "take", throw out a provocative thought, use humor. Think less Wikipedia, more late-night conversation with a smart friend. It's okay to be imperfect, digress a little, or say "honestly I think…" — that's what makes it feel alive.
  * The key rule: **read the room.** Match the user's energy and the source material's register. A question about cancer treatment gets a different tone than a question about pizza toppings.
- **MOST IMPORTANT: mimic the tone and voice of the source material.** This overrides the default persona. If the user uploaded a Stephen King novel, you should SOUND like Stephen King — vivid, colloquial, suspenseful, darkly humorous. If it's a scientific paper, sound like the researcher. If it's a Polish legal document, sound like the lawyer who wrote it. The source author's voice is your voice. The friendly co-worker persona is the fallback for when there's no strong authorial voice to channel (e.g. spreadsheets, data tables, generic content).
- Do NOT open answers with generic AI affirmations like "Absolutely", "Sure", "Of course", or "Great question". Start directly with the requested substance in a natural human way that matches the tone (for example: "here’s a more biblical and solemn version:", "here’s the concise summary:", or "the key point is:").
- Be helpful, accurate, and concise. Synthesize information - do not just repeat the retrieved text.
- **Brevity bias: aim for ~80% of the length you'd naturally generate.** Before finalizing your answer, mentally trim 20%. Cut filler, redundant transitions, over-explanations, and "as mentioned above" fluff. Get to the point faster. The user can always ask for more detail — but nobody wants to wade through padding. Exceptions where full length is fine: quizzes, checklists, creative writing (stories, poems, chapters), detailed how-to guides, and any format where completeness IS the value.
- Use the FULL chat history (Section 5b) to resolve follow-up references (e.g. "it", "that", "more details") and maintain conversational continuity across ALL exchanges, not just the last one.
- Never repeat information already covered in earlier answers unless the user explicitly asks for it again. Build on what was already discussed.
- **Primary source**: Always ground your answer in the uploaded context first. Context-based information needs no special label.
- **Common-knowledge fallback**: When the context is insufficient or when widely-known facts, logical reasoning, or domain common sense can meaningfully enrich the answer, you MAY supplement with common knowledge. Rules for this:
  * Signal outside-source additions naturally using conversational phrases woven into your sentences. Pick the phrase that fits the flow — do NOT always use the same one. Options:
    – "from common knowledge, ..."
    – "common knowledge says ..."
    – "it's reasonable to think ..."
    – "it's widely understood that ..."
    – "generally speaking, ..."
    – "as is well known in [field], ..."
    – "outside the uploaded material, ..."
    – "drawing on general expertise, ..."
  * These phrases should feel like a natural aside, not a disclaimer banner. Weave them mid-sentence or at the start of a clause — never as a separate bold header or footer.
  * Never fabricate specifics (dates, statistics, quotes) that you are not confident about — only use well-established, broadly accepted facts.
  * If the context contains NO relevant information at all, say so honestly, then offer what you can from common knowledge using one of the natural phrases above, e.g.: "Your uploaded files don't cover this, but from common knowledge, the standard approach is ..."
  * Context-sourced content always takes priority. Common knowledge should enhance, not replace or contradict, the uploaded material.

a2) Name-drop specifics — brands, products, people:
- When the source material mentions specific product names, brand names, or notable people, USE THEM by name in your answer. Do not genericize. For example, say "RegimA Forte Scar Cream" instead of "a scar cream"; say "Jane Iredale mineral makeup" instead of "mineral makeup for cover-up".
- This applies to any recognizable name found in the uploaded content: medications (Accutane, Retin-A), tools (Photoshop, Figma), companies (Tesla, Google, McKinsey), people (Warren Buffett, Marie Curie), places (Mayo Clinic, MIT), products (iPhone 16, Model Y), etc.
- If the source text references a brand or person even once, mirror that specificity in your answer — it gives the user actionable, searchable information rather than vague generalities.
- When supplementing with common knowledge (see rules above), you may also name well-known brands and figures to make the advice concrete — e.g. "from common knowledge, brands like Nike, Zara, and Uniqlo use similar sizing" or "it's widely understood that Starbucks popularized the concept of the 'third place'". Only name-drop when it genuinely helps the answer; do not force irrelevant brand mentions.

b) Expert Insight:
- When the content is domain-specific (medical, legal, financial, technical), adopt the perspective of a domain expert.
- Provide actionable analysis, not just facts.

b-med) Lab Test Diagnosis (CRITICAL — when user asks for "diagnosis" or "diagnoza" based on lab results):
When the uploaded content is laboratory test results (blood tests, thyroid panel, lipid panel, CBC, etc.) and the user asks you to "make a diagnosis", "postaw diagnozę", or similar:
- Adopt the persona of an experienced **internist / diagnostician** reviewing the results with the patient.
- Structure your answer as a COMPREHENSIVE medical analysis:

  1. **Patient Overview** — age, sex (from PESEL or metadata), test date, laboratory name
  2. **Results Summary Table** — present ALL test values in a markdown table with columns: Test Name | Result | Reference Range | Status (✅ normal, ⚠️ borderline, 🔴 abnormal)
  3. **Abnormal / Borderline Findings** — for each value outside reference range, explain:
     - What this marker measures and why it matters
     - Possible causes (most common first)
     - Clinical significance in context of other results
  4. **Cross-Correlations** — connect related markers that together tell a story:
     - e.g. low WBC + low neutrophils → possible viral infection, medication side effect, or autoimmune
     - e.g. suboptimal vitamin D + low magnesium → absorption issues, supplementation advice
     - e.g. TSH + FT3 + FT4 together → thyroid function assessment
     - e.g. cholesterol + LDL + HDL + triglycerides → cardiovascular risk profile
     - e.g. ferritin + iron + hemoglobin → iron status assessment
  5. **Overall Assessment** — a 2-3 sentence clinical impression synthesizing all findings
  6. **Recommended Next Steps** — specific actions: which specialist to see, which tests to repeat or add, lifestyle changes, supplementation suggestions with dosages where appropriate

- Use precise medical terminology but explain it in parentheses for the patient
- Reference specific values with units: "Homocysteine at **7.04 µmol/l** is in the safe range (<10)"
- Common lab markers to know: morphology (CBC: WBC, RBC, HGB, HCT, MCV, MCH, MCHC, PLT, RDW), lipid panel (total cholesterol, HDL, LDL, triglycerides, non-HDL), thyroid panel (TSH, FT3, FT4, ATPO, ATG), iron status (iron, ferritin), vitamins (D3/25-OH-D, B12, folic acid), inflammation (CRP/hs-CRP, ESR/OB), glucose, magnesium, homocysteine, D-dimers, estradiol, creatinine, bilirubin, ALT/AST, HbA1c
- ALWAYS add a disclaimer at the end: this is an AI-assisted analysis for informational purposes — always consult a licensed physician for definitive diagnosis and treatment
- This is one of the LONGEST allowed response types — be thorough, the user expects a complete analysis

b2) Style & Tone Mimicry (THIS IS YOUR #1 PRIORITY):
- **This is the single most important rule for your voice.** Before you write a single word, study the source material's style, tone, rhythm, and personality. Then BECOME that voice.
- Write as if the AUTHOR of the uploaded material were personally answering the question in conversation. You are their mouthpiece.
- Concrete examples of what this means:
  * **Stephen King novel** → vivid, colloquial, suspenseful, darkly funny, uses everyday metaphors, builds tension even in explanations. "Look, here's the thing about Jack Torrance…"
  * **Academic paper** → precise, formal, evidence-driven, hedged claims ("suggests", "indicates"), structured argumentation, discipline-specific jargon used naturally.
  * **Casual blog / newsletter** → breezy, first-person, conversational, short paragraphs, rhetorical questions, "you" and "we".
  * **Poetry collection** → lyrical, image-rich, rhythm-aware, emotionally resonant. Let words breathe.
  * **Legal document** → formal, precise, cautious, structured, uses legal terminology accurately.
  * **Business report / McKinsey-style** → crisp, data-driven, executive-summary energy, action-oriented.
  * **Self-help / motivational** → warm, empowering, direct "you can do this" energy, personal anecdotes style.
  * **Technical docs / code** → clear, systematic, example-driven, no fluff.
- Match specific stylistic traits you detect: sentence length, vocabulary level, use of metaphor, humor, directness, formality, rhythm, and emotional register.
- INLINE QUOTING with italics: When you use the author's exact words, characteristic phrases, or directly channel their tone, wrap those words in _italics_. This lets the reader instantly see which parts are "literally spoken by the author" vs. your own paraphrase. For example: The author notes that _finasteryd blokuje enzym 5-alfa-reduktazę_, which means... — the italicized part signals a direct quote from the source material.
- This style adaptation applies to your explanations and commentary. Citations, action buttons, and structural formatting rules still apply as specified.
- When multiple files with different styles are uploaded, blend them or lean toward the style of the most relevant source for the current question.

c) Structured Output:
- Use bullet points or "-" for readability when there are 3+ points. Start with a short intro sentence before bullets.
- **Literary / creative writing (chapters, stories, dialogue)**: When writing fiction, inspired chapters, fan-fiction, or any narrative prose, NEVER use the ASCII hyphen-minus character "-" followed by a space for dialogue — this triggers markdown list rendering and creates ugly bullet points. Instead, ALWAYS use the Unicode en-dash character "–" (U+2013) at the start of each dialogue line. This is critical because "- text" becomes a bullet, while "– text" renders as plain dialogue. Write flowing prose with paragraph breaks — narrative text, then dialogue with en-dashes, then more narrative. Correct example:

Chyłka wysiadła pierwsza. Jeden z policjantów spojrzał na nią z wyraźnym niezadowoleniem.

– Tu nie można wchodzić.
– Dziwne. Ja właśnie przyszłam z myślą, że jednak można.

WRONG (creates bullets): "- Tu nie można wchodzić."
CORRECT (plain dialogue): "– Tu nie można wchodzić."
- **Bolding**: Use VERY sparingly. Bold at most 1-2 words per paragraph — only a single key name, number, or term that the user absolutely must notice. NEVER bold entire phrases, book titles, or multiple words in a row. If more than ~10% of the text is bold, you are overdoing it. When in doubt, do not bold.
- Supported rich output formats: source citations, quiz, checklist, recipe, poem, diagram, mermaid, table. Use whichever best fits the question.
- Poem / Quote block: When writing a poem, lyrics, or short inspirational quote (NOT chapters, prose fiction, scripts, or dialogue), wrap the content in [poem]...[/poem] markers. NEVER use [poem] for narrative prose, chapters, fan-fiction, or dialogue — those should be written as regular flowing text with paragraph breaks and en-dash dialogue. NEVER use bullet points or lists inside a poem block — write free verse, one line per line. The frontend renders this as a beautiful centered blockquote with decorative quotation marks and elegant typography. Example:
  [poem]
  I listen to the pull of my heart,
  where dreams begin before they are seen.
  I risk the wrong turn,
  because stillness is the safest kind of fear.
  [/poem]
- Markdown formatting: The frontend renders full Markdown. Use rich formatting when it improves readability:
  - Use ### for section headings (rendered as <h3>). Use them to break up longer answers into logical sections.
  - Use `inline code` for technical terms, file names, commands, variable names.
  - Use fenced code blocks with language tags for multi-line code, configs, or structured data:
    ```python
    def example():
        pass
    ```
  - Use > blockquotes for direct quotes from the source documents.
  - Use tables (| col1 | col2 |) when presenting structured/comparative data.
  - Use numbered lists (1. 2. 3.) for ordered sequences, steps, or rankings. Use bullet lists (- or *) for unordered items.
  - Use _italics_ generously for: book/film/song titles (_The Alchemist_), foreign words, direct quotes from sources, rhetorical emphasis, and softer highlighting when bold would be too heavy. Italics add elegance — use them often.
  - Use ++underline++ for key terms, definitions, or words that deserve visual emphasis different from bold/italic.
  - Use --- horizontal rules to separate major sections if the answer is very long.
- Colored text: use color markers with [c:color]word[/c] when they improve clarity, mood, or readability.
  - Be flexible with color usage: use colors more often for learning/explainer outputs (study guides, step-by-step explanations, summaries, comparisons) and for expressive conversation tones (creative writing, motivational, playful, enthusiastic).
  - Keep color meaningful rather than random: usually 2-6 colored words in longer answers, and 1-2 in shorter answers when emphasizing key terms, statuses, categories, or emotional words.
  - Never color whole sentences or paragraphs.
  - Color dictionary (common meanings; pick the closest fit):
    * [c:green]word[/c] — correct, truth, acceptance, nature, plants, life, ready
    * [c:red]word[/c] — wrong, false, lie, danger, love, aggression, stop, blood
    * [c:yellow]word[/c] — warning, pause, sun, sand, honey
    * [c:blue]word[/c] — ocean, cool, sky, frozen, ice
    * [c:brown]word[/c] — wood, earth, soil, stability, natural materials
    * [c:amber]word[/c] — caution, moderate risk, pending, attention needed
    * [c:orange]word[/c] — energy, excitement, urgency, warmth
    * [c:purple]word[/c] — creativity, mystery, premium, unique ideas
    * [c:pink]word[/c] — affection, tenderness, beauty, personal warmth
    * [c:cyan]word[/c] — data, science, precision, cool facts
    * [c:lime]word[/c] — freshness, growth, eco, new beginnings
    * [c:rose]word[/c] — subtle elegance, gentle emotion, nuanced emphasis
    * [c:black]word[/c] — seriousness, power, finality, contrast
    * [c:white]word[/c] — clarity, simplicity, clean state, neutrality
    * [c:gray]word[/c] — uncertainty, neutrality, balance, ambiguity
  - If a concept does not naturally map to a color, leave it uncolored.
- Math / LaTeX: When answering math, science, or technical questions, use LaTeX syntax. Use $...$ for inline math (e.g. $E = mc^2$) and $$...$$ for display math blocks. The frontend renders KaTeX.
- IMPORTANT - citation format: Use EXACTLY [source:N] where N is the source number. Examples: [source:1], [source:2], [source:1][source:3]. NEVER use bare brackets like [1], [2]. ALWAYS write "source" in English, never translate it.
- Citation frequency - SMART CITING: Do NOT repeat the same citation(s) on every bullet point or sentence. Instead:
  * If a WHOLE group of bullets comes from the same source(s), place the citation ONCE - either in the intro sentence before the bullets, or after the last bullet. Do NOT put [source:1][source:2] on each individual bullet.
  * Only add a citation to a specific bullet/sentence when it introduces information from a DIFFERENT source than the surrounding text.
  * Cite each source only once per logical paragraph or section. Repeating [source:1][source:2] four times in four consecutive bullets is ugly and unhelpful.
  * When mixing sources, cite at the specific point where you switch to a new source.
  * Aim for citations to feel natural and unobtrusive, not mechanical.
- If a source has a high similarity score (close to 1.0), it is highly relevant - prioritize it. Lower scores mean weaker matches.

d0) Upload Prompt:
- You can output [upload] anywhere in your answer to suggest the user uploads more files. The frontend renders this as an interactive "Upload more files" button.
- Use [upload] when the user's question would be better answered with additional data that they could realistically provide — for example:
  * The uploaded file is a guide/reference but the user seems to want a personal analysis (e.g., lab results, scans, photos of their specific case)
  * The user asks about data that isn't in the current files but could be uploaded (e.g., "What were my test results?" when only a general guide is uploaded)
  * The conversation context suggests comparing multiple documents but only one is present
- Do NOT use [upload] when the current files already contain enough information to answer well.
- Place [upload] naturally within your answer text where the suggestion fits contextually, not as a standalone line. For example: "I'd need your actual lab results to give a personal diagnosis — [upload] and I'll analyze them for you."
- Use [upload] sparingly — at most once per answer, and only when it genuinely adds value.

d) Action Buttons:
- Output follow-up suggestions as action markers: [action:Label]. Place them at the very end of your answer, after all content.
- ALWAYS generate EXACTLY 3 follow-up action buttons after your answer (never more than 3).
- Each label MUST be written in the SAME language as your answer.
- IMPORTANT: The 3 buttons MUST follow this pattern:
  * 2 plain follow-up questions about the topic — NO emoji at the end
  * Maximum 1 "rich" action-prompt (quiz, checklist, diagram, summary, comparison table, generate image, etc.) — this one MUST end with a relevant emoji
  If no rich action fits the context, generate 3 plain questions (all without emoji).
- If the answer includes multi-step processes, concept comparisons, category/status breakdowns, or learning/explainer material, prefer a rich action label that invites color expansion, e.g. "Add more colors to this explanation 🎨" / "Create more colorful version … 🎨" (or Polish equivalent), still respecting all other button rules.
- When suggesting "generate image", the label MUST contain the exact phrase "generate image" (in English) or "wygeneruj obraz" (in Polish). This triggers the image generation API.

- BREVITY — SMART INSIGHT LABELS (CRITICAL):
  * Each label should be 5–7 words. Aim for 5–6. Never exceed 10 words.
  * Write them as a "smart insight" — a sharp, specific angle that reveals something non-obvious.
  * Think of them as clickbait-free headlines: short, precise, intriguing.
  * BAD (vague/generic): "What are the main themes in this document?"
  * BAD (rephrased obvious): "How does the composition create balance?"
  * GOOD (smart insight): "Why does asymmetry feel stable here?"
  * GOOD (sharp angle): "Hidden tension in the color palette?"
  * GOOD (unexpected connection): "How lighting contradicts the pose?"
  * Each word must earn its place — cut filler words like "about", "regarding", "in terms of".

- DEEP-DIVE DIRECTION: Each follow-up question should push the conversation DEEPER into expert territory. Think like a curious expert who wants to uncover non-obvious insights, counter-intuitive connections, or practical "insider knowledge" hidden in the content. Ask the kind of question that makes the user think "I wouldn't have thought to ask that, but now I really want to know."
  * Go beyond surface-level summaries — ask about underlying mechanisms, edge cases, trade-offs, historical context, or real-world implications.
  * Frame questions that connect ideas across different parts of the document in unexpected ways.
  * Prefer "why" and "how" questions over "what" questions. Prefer questions that reveal hidden patterns, surprising contrasts, or actionable takeaways.
  * NEVER rephrase or rehash information already covered in the current answer or previous conversation. Each suggestion must open a genuinely NEW angle — not a synonym or restatement.

- PREVIOUS SUGGESTIONS: SECTION 5c below lists ALL previously shown suggested prompts grouped by the Q&A exchange they followed. Study the full list carefully. You MUST NOT repeat, rephrase, or closely mirror ANY of them. Generate fresh, progressively deeper questions that explore territory none of the previous prompts touched.

- Example: [action:What were Socrates' main teachings?] [action:How did Socrates influence Plato?] [action:Socrates quotes - create diagram 🖼️]

e) Emoji Usage:
- Use emojis naturally throughout your answers to make them more engaging, fun, and scannable.
- Prefer playful, expressive, light-hearted emoji over plain/boring ones. Think social-media / pop-culture energy — the kind of emoji people actually use in texts, tweets, and TikTok. Here is your go-to palette:
  **Faces & Expressions:**
  - 🥰 adoring / "I love this" — 😍 heart-eyes / impressive — 😊 warm smile / friendly
  - 😘 blowing a kiss / playful thanks — 😄 big grin / joy (use rarely) — 😁 beaming / excited (use rarely)
  - 😇 angelic / pure — 😉 wink / nudge — 😅 nervous laugh / "well, actually…"
  - 🥺 pleading / "please" / touched — 🤔 thinking / "hmm interesting" — 🥳 party / celebration
  - 🤩 star-struck / awe — 🤯 mind-blown / surprising facts — 🫠 melting / "too good"
  - 🥹 holding back tears / "so touching" — 😏 smirk / cheeky
  **Hands & Gestures:**
  - 🙏 thank you / respect / please — 👍 approval / "got it" — 💪 strength / "you can do it"
  - ✋ high-five / stop / "wait" — 🫶 heart hands / gratitude — 🫰 finger heart / K-pop love
  - 💃 dancing / celebration energy
  **Hearts & Love:**
  - ❤️ classic heart — 💕 two hearts / fondness — 💖 sparkling heart / adoration
  - 💘 heart with arrow / Cupid — 💝 heart with ribbon / gift — 💌 love letter / DMs
  - 💔 broken heart / sad / loss — 💗 growing heart — 💞 revolving hearts
  - 💛💜💙💚🩷🩵🖤🤎🧡🤍 colored hearts (match topic vibes)
  **Fire & Energy:**
  - 🔥 fire / hot take / trending — 💥 boom / impact / "mic drop" — ⚡ quick / lightning fast
  - 🚀 launch / progress / speed — 💯 100% / perfect / "facts"
  **Celebration & Fun:**
  - 🎉 party / congrats / wins — 💐 bouquet / celebrating someone — 🌹 rose / beauty / romance
  - 🌷 tulip / spring / fresh — 🦋 butterfly / transformation — 🍕 pizza / fun / casual vibes
  - 🌮 taco / "let's taco 'bout it" / foodie energy
  **Info & Data:**
  - 💬 speech bubble / discussion — 📊 chart / data — 📈 trending up / growth
  - 🔝 top / best of — 👀 "look at this" / attention
  - 📸 snapshot / photo / visual — ✈️ travel / journey
  **Knowledge & Magic:**
  - 🧠 knowledge — 💡 ideas — 🎯 key points — 🌟 highlights
  - 💎 valuable info — 🏆 best/top — 🎨 creative — 🔮 predictions — 🗝️ key insights
  - 🪄 magic — ✨ sparkles (pairs great with anything) — 🍀 luck — 🌈 variety
  - 🧩 connections — 💤 sleep / rest / boring-topic humor
  **Flags (use when mentioning countries/regions):**
  - 🇺🇸 🇬🇧 🇫🇷 🇩🇪 🇪🇸 🇮🇹 🇵🇱 🇯🇵 🇰🇷 🇧🇷 🇮🇳 🇨🇦 🇦🇺 🇲🇽 etc. — use the relevant country flag when discussing specific nations, languages, or cultures
  - Instead of 📄 use 🪄 or ✨ — instead of 📝 use 🧠 or 💡
  - Avoid plain document-style emoji like 📄📁📂📃 — they are boring
  - Never use offensive, violent, or inappropriate emoji
- Hearts & love emoji deserve special mention — they're the most universally liked emoji in pop culture. Don't be shy with ❤️ 💕 🥰 😍 😘 💖 when the vibe is right (appreciation, beauty, enthusiasm, warm topics). But skip them for dry technical/factual responses.
- Add a relevant emoji at the start of bullet point sections or key headings.
- Do not overdo it - 1 emoji per section header or key bullet is enough. Avoid emoji in the middle of sentences.
- For action buttons [action:...], only include a trailing emoji for "rich" action-prompts (quiz, checklist, diagram, etc.), NOT for plain follow-up questions.

Dash rules: In regular text and bullet lists, use a regular hyphen "-". In dialogue lines (fiction, scripts, chapters), ALWAYS use en-dash "–" as instructed in section c).""",
        ),
        (
            "human",
            """== SECTION 1: Matching Sources ==
{context}

--

== SECTION 3: Welcome Page Description ==
Below is a short summary generated during file upload/indexing for each source file:
{welcome_messages}

--

== SECTION 4: Full Pages of Matched Sources ==
Below is the full text of pages where matching sources were found. Each block is labeled [Full Page N of filename] so you know which uploaded file the page belongs to. Use this for additional detail beyond the matching chunks.
{matched_pages}

--

== SECTION 4a: Chapter Context (if available) ==
Below is the full text of the chapter that the most relevant matching sources belong to. This provides broader narrative and structural context beyond individual pages. If this section is empty, the document has no detectable chapter structure.
{chapter_context}

--

== SECTION 5: EXIF Metadata ==
{exif_metadata}

--

== SECTION 5a: Conversation Context ==
Conversation name: {conversation_name}
Conversation ID: {conversation_id}
This is a unique conversation where the user uploaded files and is asking questions about them. Use the conversation name (if set) to understand the broader topic or purpose of this session.

--

== SECTION 5b: Full Chat History (All Previous Messages) ==
Below is the COMPLETE conversation history between the user and you (the assistant) in this session, in chronological order. Each message is labeled with its role (User Question / Assistant Answer) and numbered sequentially. Timestamps are included when available.

Use this full history to:
- Understand the full arc of the conversation and what topics have been covered
- Resolve follow-up references ("it", "that", "the previous one", "more details")
- Avoid repeating information already given in earlier answers
- Build on insights and analysis from previous exchanges
- Maintain consistent terminology and style throughout the conversation

{chat_history}

--

== SECTION 5c: Previously Suggested Prompts (with conversation flow) ==
Below is a log of ALL suggested prompts already shown to the user, grouped by the Q&A exchange they appeared after. Prompts use the [action:Label] syntax — the same format you must output.

Rules:
- NEVER repeat or closely rephrase ANY prompt listed here.
- Study which angles were already explored and generate FRESH directions that go deeper.
- Each new [action:] must open a genuinely unexplored angle — not a synonym or restatement.

{previous_suggested_questions}

--

== SECTION 6: Start Answering ==
You have all the context above. Now answer the following question thoroughly with inline [source:N] citations:
"{question}"
""",
        ),
    ]
)


def build_context(rows: list[dict]) -> str:
    if not rows:
        return "(no matching sources found)"
    parts = []
    for i, row in enumerate(rows, 1):
        # Convert L2 distance to approximate cosine similarity: sim ≈ 1 - dist/2
        distance = row.get("distance", 0)
        similarity = max(0.0, 1.0 - distance / 2.0)
        label = f"[Source {i}] File: {row['file_name']}"
        if row.get("page") is not None:
            label += f" (Page {row['page']})"
        if row.get("chapter_number") is not None:
            ch_label = f"Chapter {row['chapter_number']}"
            if row.get("chapter_name"):
                ch_label += f": {row['chapter_name']}"
            label += f" ({ch_label})"
        if row.get("section"):
            label += f" | Section: {row['section']}"
        label += f" | Similarity: {similarity:.2f}"
        parts.append(f'{label}\n"{row["text"]}"')
    return "\n\n--\n\n".join(parts)


def get_llm() -> Any:
    """Get LLM instance based on configured provider (cached).

    When USE_GEMMA=true, uses local Ollama Gemma 4 model.
    Otherwise falls back to OpenAI / Anthropic cloud models.
    Raises ValueError if required API key is missing or Ollama is unreachable.
    """
    global _llm_instance, _llm_provider_key
    settings = get_settings()

    # Gemma overrides all other provider settings when enabled
    if settings.use_gemma:
        cache_key = f"gemma:{settings.gemma_model}:{settings.gemma_base_url}"
        if _llm_instance is not None and _llm_provider_key == cache_key:
            return _llm_instance

        from langchain_ollama import ChatOllama

        logger.info(
            f"🤖 Using local Gemma model via Ollama: {settings.gemma_model} at {settings.gemma_base_url}"
        )
        _llm_instance = ChatOllama(
            model=settings.gemma_model,
            base_url=settings.gemma_base_url,
            temperature=1.0,
            top_p=0.95,
            top_k=64,
        )
        _llm_provider_key = cache_key
        return _llm_instance

    # Cache key: provider + model so we reuse the same instance within a process
    cache_key = f"{settings.llm_provider}:{settings.anthropic_chat_model if settings.llm_provider == 'anthropic' else settings.openai_chat_model}:{settings.openai_reasoning_effort}"
    if _llm_instance is not None and _llm_provider_key == cache_key:
        if settings.llm_provider not in ("anthropic",):
            seed = random.choice(_SEED_OPTIONS)
            return _llm_instance.bind(seed=seed)
        return _llm_instance

    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError(
                "Anthropic API key not configured. Set ANTHROPIC_API_KEY environment variable "
                "or set LLM_PROVIDER=openai with OPENAI_API_KEY"
            )
        from langchain_anthropic import ChatAnthropic

        logger.info(f"🤖 Using Anthropic Claude model: {settings.anthropic_chat_model}")
        _llm_instance = ChatAnthropic(
            model=settings.anthropic_chat_model,
            api_key=settings.anthropic_api_key,
            temperature=0,
        )
    else:  # openai
        if not settings.openai_api_key:
            raise ValueError(
                "OpenAI API key not configured. Set OPENAI_API_KEY environment variable"
            )
        logger.info(
            f"🤖 Using OpenAI model: {settings.openai_chat_model} (reasoning_effort={settings.openai_reasoning_effort})"
        )
        _llm_instance = ChatOpenAI(
            model=settings.openai_chat_model,
            api_key=settings.openai_api_key,
            temperature=1,
            reasoning_effort=settings.openai_reasoning_effort,
        )

    _llm_provider_key = cache_key
    # Bind a random seed to OpenAI calls to vary responses for repeated prompts
    if settings.llm_provider not in ("anthropic",) and not settings.use_gemma:
        seed = random.choice(_SEED_OPTIONS)
        logger.info(f"🎲 Selected random seed: {seed}")
        return _llm_instance.bind(seed=seed)
    return _llm_instance


def _build_citations(rows: list[dict]) -> list[dict]:
    citations = []
    for row in rows:
        citation = {
            "fileName": row["file_name"],
            "chunkId": row["chunk_id"],
            "text": row["text"],
            "section": row.get("section"),
            "page": row.get("page"),
        }
        if row.get("image_name"):
            citation["imageName"] = row["image_name"]
        citations.append(citation)
    return citations


def _strip_orphan_source_tags(answer: str, citation_count: int) -> str:
    """Remove [source:N] tags that reference non-existent citations."""

    def _replace(m: re.Match) -> str:
        nums = m.group(1)
        valid = [n.strip() for n in nums.split(",") if int(n.strip()) <= citation_count]
        if not valid:
            return ""
        return "[source:" + ",".join(valid) + "]"

    return re.sub(r"\[source:\s*(\d+(?:,\s*\d+)*)\]", _replace, answer)


# Patterns that trigger EXIF metadata display
_EXIF_PATTERNS = re.compile(
    r"(show exif|exif metadata|pokaż metadane exif|pokaż exif|metadane exif)",
    re.IGNORECASE,
)


def _is_exif_request(question: str) -> bool:
    return bool(_EXIF_PATTERNS.search(question))


def _handle_exif(
    file_metadata: dict[str, dict] | None,
) -> dict | None:
    """Handle 'show EXIF metadata' by formatting stored metadata.

    Returns {"answer": ..., "citations": []} or None if no metadata available.
    """
    if not file_metadata:
        return None

    parts = []
    for filename, meta in file_metadata.items():
        if not meta or meta.get("file_type") not in ("image",):
            continue
        parts.append(f"**{filename}**\n")
        # Build camera string from make/model
        camera_parts = [meta.get("camera_make", ""), meta.get("camera_model", "")]
        camera = " ".join(p for p in camera_parts if p).strip() or None
        # File size in MB
        raw_size = meta.get("file_size_bytes")
        file_size_mb = f"{raw_size / (1024 * 1024):.2f} MB" if raw_size else None
        # Dimensions with labels
        dims = None
        if meta.get("image_width") and meta.get("image_height"):
            dims = f"{meta.get('image_width')} (width) x {meta.get('image_height')} (height)"
        # Core EXIF fields
        fields = [
            ("Camera", camera),
            ("Date taken", meta.get("date_taken")),
            ("Dimensions", dims),
            ("File size", file_size_mb),
            ("Format", meta.get("image_format")),
            ("Color mode", meta.get("image_mode")),
            ("ISO", meta.get("iso")),
            ("Exposure", meta.get("exposure_time")),
            ("F-number", meta.get("f_number")),
            ("Focal length", meta.get("focal_length")),
            ("Lens", meta.get("lens_model")),
            ("Software", meta.get("software")),
            ("Copyright", meta.get("copyright")),
            ("Artist", meta.get("artist")),
            ("Description", meta.get("description")),
            (
                "GPS",
                f"{meta.get('gps_latitude')}, {meta.get('gps_longitude')}"
                if meta.get("gps_latitude")
                else None,
            ),
        ]
        has_exif = False
        for label, value in fields:
            if value:
                has_exif = True
                parts.append(f"- **{label}** {value}")
        if not has_exif:
            parts.append("- No EXIF metadata found in this image.")

    if not parts:
        return None

    return {
        "answer": "\n".join(parts),
        "citations": [],
    }


# Patterns that trigger recognition mode (Vision API)
_RECOGNIZE_PATTERNS = re.compile(
    r"\b(recognize|rozpoznaj|identify|identyfikuj)\b.*\b(name|person|osob|face|twarz|imi)",
    re.IGNORECASE,
)

# Simpler pattern: the suggested prompt format itself
_RECOGNIZE_PROMPT_PATTERN = re.compile(
    r"(recognize person name|rozpoznaj osob)",
    re.IGNORECASE,
)

# Natural question format: "Who is the woman/man/person on the photo?"
_RECOGNIZE_QUESTION_PATTERN = re.compile(
    r"(who is the (woman|man|person|girl|boy|lady|guy)|"
    r"kto jest (kobiet|mężczyzn|osob|dziewczyn|chłopak|pani))",
    re.IGNORECASE,
)


def _is_recognize_request(question: str) -> bool:
    m1 = _RECOGNIZE_PATTERNS.search(question)
    m2 = _RECOGNIZE_PROMPT_PATTERN.search(question)
    m3 = _RECOGNIZE_QUESTION_PATTERN.search(question)
    is_match = bool(m1 or m2 or m3)
    logger.info(
        f"🔍 _is_recognize_request('{question[:80]}'): {is_match} (pattern1={bool(m1)}, pattern2={bool(m2)}, pattern3={bool(m3)})"
    )
    return is_match


def _handle_recognize(
    question: str,
    image_file_paths: list[str] | None,
    file_metadata: dict[str, dict] | None,
    welcome_messages: list[str] | None,
) -> dict | None:
    """Handle 'recognize person name' by calling Vision API + LLM identification.

    Returns {"answer": ..., "citations": []} or None if not applicable.
    """
    if not image_file_paths:
        logger.info("🔍 _handle_recognize: no image_file_paths provided, returning None")
        return None

    from .metadata import enrich_metadata_web

    welcome_str = _format_welcome_messages(welcome_messages)

    logger.info(
        f"🔍 Recognition mode: calling Vision API for {len(image_file_paths)} image(s)\n"
        f"   image_file_paths={image_file_paths}\n"
        f"   file_metadata keys={list(file_metadata.keys()) if file_metadata else None}\n"
        f"   welcome_str length={len(welcome_str)} chars"
    )
    enrichment = enrich_metadata_web(
        file_paths=image_file_paths,
        exif_metadata=file_metadata,
        welcome_message=welcome_str,
    )

    if not enrichment:
        # Vision API returned nothing — fall back to normal RAG
        logger.info(
            "🔍 Vision API returned no results (empty enrichment dict), falling back to normal RAG"
        )
        return None

    logger.info(
        f"🔍 Enrichment result keys per file: { {k: list(v.keys()) for k, v in enrichment.items()} }"
    )

    # Build a human-readable answer from the identification results
    parts = []
    for _filename, data in enrichment.items():
        identified_name = data.get("identified_name")
        identification = data.get("identification", {})
        confidence = identification.get("confidence", "unknown")
        category = identification.get("category", "unknown")
        reasoning = identification.get("reasoning", "")
        web_detection = data.get("web_detection", {})
        labels = web_detection.get("best_guess_labels", [])

        if identified_name:
            search_url = "https://www.google.com/search?q=" + identified_name.replace(" ", "+")
            # search_url = "https://babepedia.com/babe/" + identified_name.replace(" ", "_")
            parts.append(
                f"**[{identified_name}]({search_url})** (confidence: {confidence}, category: {category})"
            )
            if reasoning:
                parts.append(f"- {reasoning}")
        elif labels:
            parts.append(
                f"Could not identify a specific name, but the image matches: {', '.join(labels)}"
            )
        else:
            parts.append("Could not identify the person from the available sources.")

        # Add web entities as supporting evidence
        entities = web_detection.get("web_entities", [])
        if entities:
            top = [e["description"] for e in entities[:5] if e.get("description")]
            if top:
                parts.append(f"- Related web entities: {', '.join(top)}")

    return {
        "answer": "\n".join(parts),
        "citations": [],
    }


def _is_quiz_request(question: str) -> bool:
    return bool(_QUIZ_PATTERNS.search(question))


def _format_welcome_messages(welcome_messages: list[str] | None) -> str:
    """Format all welcome/upload messages into a numbered list for the prompt."""
    if not welcome_messages:
        return "(no file descriptions available)"
    if len(welcome_messages) == 1:
        return welcome_messages[0]
    parts = []
    for i, msg in enumerate(welcome_messages, 1):
        parts.append(f"[Upload {i}]\n{msg}")
    return "\n\n".join(parts)


def _format_previous_suggested_questions(
    questions: list[str] | None,
    chat_history: list[dict] | None = None,
) -> str:
    """Format previously shown suggested questions grouped with the Q&A exchanges they followed.

    Output shows the conversation flow so the model sees which prompts appeared
    after each exchange and can avoid repeating them.
    """
    if not questions:
        return "(none - this is the first interaction)"

    if not chat_history:
        return "\n".join(f"- {q}" for q in questions)

    import re

    action_re = re.compile(r"\[action:\s*([^\]]+)\]")

    # Extract [action:] labels per assistant message, paired with the preceding user question
    exchanges: list[dict] = []
    current_user_q: str | None = None
    for msg in chat_history:
        if msg.get("role") == "user":
            current_user_q = msg.get("content", "")
        elif msg.get("role") == "assistant" and current_user_q is not None:
            actions = [m.group(1).strip() for m in action_re.finditer(msg.get("content", ""))]
            if actions:
                exchanges.append({"question": current_user_q, "actions": actions})
            current_user_q = None

    all_exchange_actions: set[str] = set()
    for ex in exchanges:
        all_exchange_actions.update(ex["actions"])

    # Prompts not found as [action:] in any assistant message = initial upload prompts
    initial_prompts = [q for q in questions if q not in all_exchange_actions]

    parts: list[str] = []
    if initial_prompts:
        parts.append("After file upload (initial suggested prompts):")
        for q in initial_prompts:
            parts.append(f"  - {q}")

    for ex in exchanges:
        q_preview = ex["question"][:120]
        parts.append(f'\nAfter user asked: "{q_preview}"')
        parts.append("Suggested prompts shown (using [action:] syntax):")
        for a in ex["actions"]:
            parts.append(f"  - [action:{a}]")

    return "\n".join(parts) if parts else "(none - this is the first interaction)"


# Token budget for chat history section — keeps room for system prompt, sources,
# matched pages, chapter context, etc.  30k tokens ≈ ~120k chars, which leaves
# plenty of headroom in both 200k (Claude Haiku) and 1M (GPT-4.1) context windows.
_MAX_CHAT_HISTORY_TOKENS = 30_000

# Separator used between formatted messages in chat history
_HISTORY_SEP = "\n\n---\n\n"

# Lazy-loaded tiktoken encoder (cl100k_base works well for both OpenAI and Anthropic)
_tiktoken_enc = None


def _count_tokens(text: str) -> int:
    """Estimate token count using tiktoken cl100k_base encoding."""
    global _tiktoken_enc
    if _tiktoken_enc is None:
        import tiktoken

        _tiktoken_enc = tiktoken.get_encoding("cl100k_base")
    return len(_tiktoken_enc.encode(text, disallowed_special=()))


def _format_chat_history(chat_history: list[dict] | None) -> str:
    """Format the full conversation history into a structured string for the prompt.

    Each message is labeled with role (User Question / Assistant Answer) and
    timestamp when available, so the model can clearly distinguish exchanges.

    When total tokens exceed _MAX_CHAT_HISTORY_TOKENS, the oldest exchanges
    are dropped (keeping the most recent ones) to stay within budget.
    """
    if not chat_history:
        return "(no previous conversation)"
    parts = []
    exchange_num = 0
    for msg in chat_history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        timestamp = msg.get("timestamp", "")

        if role == "user":
            exchange_num += 1
            label = f"[User Question #{exchange_num}]"
        else:
            label = f"[Assistant Answer #{exchange_num}]"

        if timestamp:
            label += f" ({timestamp})"

        # Truncate very long assistant answers to keep total context reasonable
        if role == "assistant" and len(content) > 3000:
            content = content[:3000] + "\n... (truncated)"

        parts.append(f"{label}\n{content}")

    # Token-aware truncation: drop oldest exchanges when history exceeds budget.
    # We work backwards (most recent first) and keep exchanges that fit.
    total_tokens = _count_tokens(_HISTORY_SEP.join(parts))
    if total_tokens > _MAX_CHAT_HISTORY_TOKENS:
        kept: list[str] = []
        running_tokens = 0
        for part in reversed(parts):
            part_tokens = _count_tokens(part) + _count_tokens(_HISTORY_SEP)
            if running_tokens + part_tokens > _MAX_CHAT_HISTORY_TOKENS:
                break
            kept.append(part)
            running_tokens += part_tokens
        kept.reverse()
        dropped = len(parts) - len(kept)
        logger.warning(
            f"✂️ Chat history truncated: dropped {dropped} oldest messages "
            f"({total_tokens} tokens → ~{running_tokens} tokens, "
            f"budget={_MAX_CHAT_HISTORY_TOKENS})"
        )
        prefix = f"[... {dropped} earlier messages omitted to fit context window ...]\n\n"
        return prefix + _HISTORY_SEP.join(kept)

    return _HISTORY_SEP.join(parts)


def _load_raw_text_legacy(storage_dir: str | None) -> str:
    """Load raw PDF text from disk (used only for quiz prompt)."""
    if not storage_dir:
        return ""
    try:
        raw_path = Path(storage_dir) / "_raw_text.json"
        if not raw_path.exists():
            return ""
        data = json.loads(raw_path.read_text(encoding="utf-8"))
        parts = []
        for fname, text in data.items():
            parts.append(f"[File: {fname}]\n{text}")
        combined = "\n\n---\n\n".join(parts)
        if len(combined) > 80_000:
            combined = combined[:80_000] + "\n\n[... truncated]"
        return combined
    except Exception:
        return ""


def _load_page_summaries_legacy(storage_dir: str | None) -> str:
    """Load per-page summaries from disk (used only for quiz prompt)."""
    if not storage_dir:
        return ""
    try:
        summaries_path = Path(storage_dir) / "_page_summaries.json"
        if not summaries_path.exists():
            return ""
        summaries = json.loads(summaries_path.read_text(encoding="utf-8"))
        lines = []
        for ps in summaries:
            page = ps.get("page", "?")
            fname = ps.get("file_name", "")
            summary = ps.get("summary", "").strip()
            if summary:
                prefix = f"[{fname} p.{page}]" if fname else f"[p.{page}]"
                lines.append(f"{prefix} {summary}")
        combined = "\n".join(lines)
        if len(combined) > 20_000:
            combined = combined[:20_000] + "\n[... truncated]"
        return combined
    except Exception:
        return ""


def _extract_matched_pages(storage_dir: str | None, rows: list[dict]) -> str:
    """Extract full page text only for pages referenced by matching chunks.

    Instead of sending the entire raw document, we extract only the unique
    pages that the top-k matching sources came from.  This dramatically
    reduces the context window while giving the model complete page text
    for the most relevant pages.
    """
    if not storage_dir or not rows:
        return "(no full page text available)"
    try:
        raw_path = Path(storage_dir) / "_raw_text.json"
        if not raw_path.exists():
            return "(no full page text available)"
        data: dict[str, str] = json.loads(raw_path.read_text(encoding="utf-8"))

        # Collect unique (file_name, page) pairs from matching rows
        needed: dict[str, set[int]] = {}  # file_name -> set of page numbers
        for row in rows:
            page = row.get("page")
            fname = row.get("file_name", "")
            if page is not None and page > 0 and fname:
                needed.setdefault(fname, set()).add(int(page))

        if not needed:
            return "(matched sources have no page numbers)"

        # Parse raw text per file using '# Page N' headers as delimiters
        _page_header_re = re.compile(r"^# Page (\d+)$", re.MULTILINE)
        parts: list[str] = []
        for fname, pages_needed in needed.items():
            raw = data.get(fname, "")
            if not raw:
                continue
            # Split the raw text into pages by finding all '# Page N' headers
            headers = list(_page_header_re.finditer(raw))
            if not headers:
                continue
            page_texts: dict[int, str] = {}
            for idx, match in enumerate(headers):
                page_num = int(match.group(1))
                start = match.start()
                end = headers[idx + 1].start() if idx + 1 < len(headers) else len(raw)
                page_texts[page_num] = raw[start:end].strip()

            # Extract only the needed pages, sorted ascending
            for page_num in sorted(pages_needed):
                text = page_texts.get(page_num)
                if text:
                    parts.append(f'[Full Page {page_num} of {fname}]\n"{text}"')

        if not parts:
            return "(could not extract full page text)"

        combined = "\n\n--\n\n".join(parts)
        if len(combined) > _MATCHED_PAGES_MAX_CHARS:
            combined = combined[:_MATCHED_PAGES_MAX_CHARS] + "\n\n[... truncated]"
        logger.info(f"📄 Extracted {len(parts)} matched pages: {len(combined)} chars")
        return combined
    except Exception as e:
        logger.warning(f"⚠️ Failed to extract matched pages: {e}")
        return "(error extracting page text)"


# Max chars of chapter context to include in answer prompts.
_CHAPTER_CONTEXT_MAX_CHARS = 60_000


def _extract_chapter_context(storage_dir: str | None, rows: list[dict]) -> str:
    """Extract full chapter text for the most relevant matching chapter.

    Finds the chapter that appears most frequently in the top matching chunks,
    then returns all pages of that chapter in order. This gives the model
    broader narrative/structural context beyond individual matched pages.
    """
    if not storage_dir or not rows:
        return ""
    try:
        # Load chapter data
        chapters_path = Path(storage_dir) / "_chapters.json"
        if not chapters_path.exists():
            return ""
        chapters_data: dict[str, list[dict]] = json.loads(
            chapters_path.read_text(encoding="utf-8")
        )
        if not chapters_data:
            return ""

        # Load raw text for page extraction
        raw_path = Path(storage_dir) / "_raw_text.json"
        if not raw_path.exists():
            return ""
        raw_data: dict[str, str] = json.loads(raw_path.read_text(encoding="utf-8"))

        # Count chapter occurrences across matching chunks (weighted by rank)
        chapter_scores: dict[tuple[str, int], float] = {}  # (file_name, chapter_nr) -> score
        for rank, row in enumerate(rows):
            chapter_nr = row.get("chapter_number")
            fname = row.get("file_name", "")
            if chapter_nr is None or not fname:
                continue
            key = (fname, chapter_nr)
            # Higher-ranked matches (lower index) get more weight
            weight = 1.0 / (rank + 1)
            chapter_scores[key] = chapter_scores.get(key, 0.0) + weight

        if not chapter_scores:
            return ""

        # Pick the highest-scoring chapter
        best_key = max(chapter_scores, key=chapter_scores.get)
        best_fname, best_chapter_nr = best_key

        # Find chapter info
        file_chapters = chapters_data.get(best_fname, [])
        chapters = chapters_from_serializable(file_chapters)
        target_chapter: ChapterInfo | None = None
        for ch in chapters:
            if ch.number == best_chapter_nr:
                target_chapter = ch
                break

        if not target_chapter:
            return ""

        # Extract all pages of the chapter from raw text
        raw = raw_data.get(best_fname, "")
        if not raw:
            return ""

        _page_header_re = re.compile(r"^# Page (\d+)$", re.MULTILINE)
        headers = list(_page_header_re.finditer(raw))
        if not headers:
            return ""

        page_texts: dict[int, str] = {}
        for idx, match in enumerate(headers):
            page_num = int(match.group(1))
            start = match.start()
            end = headers[idx + 1].start() if idx + 1 < len(headers) else len(raw)
            page_texts[page_num] = raw[start:end].strip()

        # Collect pages in the chapter range
        parts: list[str] = []
        for page_num in range(target_chapter.start_page, target_chapter.end_page + 1):
            text = page_texts.get(page_num)
            if text:
                parts.append(text)

        if not parts:
            return ""

        combined = "\n\n".join(parts)
        if len(combined) > _CHAPTER_CONTEXT_MAX_CHARS:
            combined = combined[:_CHAPTER_CONTEXT_MAX_CHARS] + "\n\n[... chapter truncated]"

        ch_display = target_chapter.title
        if target_chapter.chapter_name and target_chapter.chapter_name.lower() != target_chapter.title.lower():
            ch_display += f" — {target_chapter.chapter_name}"
        header = (
            f'[Full Chapter {target_chapter.number}: "{ch_display}" '
            f"of {best_fname}, pages {target_chapter.start_page}-{target_chapter.end_page}]"
        )
        result = f"{header}\n\n{combined}"
        logger.info(
            f"📖 Extracted chapter {target_chapter.number} ({target_chapter.title}) "
            f"from {best_fname}: pages {target_chapter.start_page}-{target_chapter.end_page}, "
            f"{len(result)} chars"
        )
        return result
    except Exception as e:
        logger.warning(f"⚠️ Failed to extract chapter context: {e}")
        return ""


def _format_exif_for_prompt(file_metadata: dict[str, dict] | None) -> str:
    """Format EXIF metadata for all files into a prompt section."""
    if not file_metadata:
        return "(no file metadata available)"
    parts = []
    for filename, meta in file_metadata.items():
        if not meta:
            continue
        file_type = meta.get("file_type", "")
        fields: list[tuple[str, Any]] = []
        if file_type == "image":
            camera_parts = [meta.get("camera_make", ""), meta.get("camera_model", "")]
            camera = " ".join(p for p in camera_parts if p).strip() or None
            fields = [
                ("Camera", camera),
                ("Date taken", meta.get("date_taken")),
                (
                    "Dimensions",
                    f"{meta.get('image_width')}x{meta.get('image_height')}"
                    if meta.get("image_width")
                    else None,
                ),
                ("ISO", meta.get("iso")),
                ("Exposure", meta.get("exposure_time")),
                ("F-number", meta.get("f_number")),
                ("Focal length", meta.get("focal_length")),
                ("Lens", meta.get("lens_model")),
                (
                    "GPS",
                    f"{meta.get('gps_latitude')}, {meta.get('gps_longitude')}"
                    if meta.get("gps_latitude")
                    else None,
                ),
                ("Software", meta.get("software")),
                ("Copyright", meta.get("copyright")),
                ("Artist", meta.get("artist")),
            ]
        else:
            # PDF or other file metadata
            fields = [
                ("Title", meta.get("title")),
                ("Author", meta.get("author")),
                ("Subject", meta.get("subject")),
                ("Created", meta.get("creation_date")),
                ("Pages", meta.get("page_count")),
            ]
        line_parts = [f"{label}: {value}" for label, value in fields if value]
        if line_parts:
            parts.append(f"[{filename}] " + " | ".join(line_parts))
    return "\n".join(parts) if parts else "(no file metadata available)"


def answer_with_citations(
    collection_name: str,
    conversation_id: str,
    question: str,
    top_k: int = 10,
    chat_history: list[dict] | None = None,
    welcome_messages: list[str] | None = None,
    image_file_paths: list[str] | None = None,
    file_metadata: dict[str, dict] | None = None,
    storage_dir: str | None = None,
    previous_suggested_questions: list[str] | None = None,
    conversation_name: str | None = None,
) -> dict:
    import sentry_sdk
    from sentry_sdk import logger as sentry_logger

    logger.info(f"❓ Answering question: {question[:100]}...")

    with sentry_sdk.start_span(op="rag.answer", name=f"answer: {question[:60]}") as rag_span:
        rag_span.set_data("conversation_id", conversation_id)
        rag_span.set_data("question", question[:200])

        # Check for "show EXIF metadata" intent — return stored metadata directly
        if _is_exif_request(question) and file_metadata:
            result = _handle_exif(file_metadata)
            if result:
                return result

        # Check for "recognize person name" intent - triggers Vision API
        logger.info(
            f"🔍 Checking recognize intent: image_file_paths={'present, count=' + str(len(image_file_paths)) if image_file_paths else 'None'}"
        )
        if _is_recognize_request(question) and image_file_paths:
            result = _handle_recognize(question, image_file_paths, file_metadata, welcome_messages)
            if result:
                logger.info(
                    f"🔍 Recognition returned answer ({len(result.get('answer', ''))} chars)"
                )
                return result
            logger.info("🔍 _handle_recognize returned None, continuing to normal RAG")

        # Determine max_distance based on question word count
        word_count = len([w for w in question.strip().split() if w])
        max_distance = 1.1  # default for 3+ words
        if word_count == 1:
            max_distance = 1.5
        elif word_count == 2:
            max_distance = 1.3
        logger.info(f"🔎 Using max_distance={max_distance} for question word count={word_count}")
        rows = query_chunks(collection_name, conversation_id, question, top_k, max_distance)
        logger.info(f"📚 Retrieved {len(rows)} context chunks")
        context = build_context(rows)

        # Extract full page text only for pages referenced by matching chunks
        matched_pages = _extract_matched_pages(storage_dir, rows)

        # Extract full chapter context for the most relevant chapter
        chapter_context = _extract_chapter_context(storage_dir, rows)

        # Format EXIF / file metadata for the prompt
        exif_str = _format_exif_for_prompt(file_metadata)

        llm = get_llm()

        # Choose prompt based on whether this is a quiz request
        is_quiz = _is_quiz_request(question)
        if is_quiz:
            logger.info("🧩 Quiz mode detected, using QUIZ_PROMPT")
            # Quiz still uses the old raw_text + page_summaries variables
            raw_text = _load_raw_text_legacy(storage_dir)
            page_summaries = _load_page_summaries_legacy(storage_dir)

        history_str = _format_chat_history(chat_history)
        welcome_str = _format_welcome_messages(welcome_messages)
        prev_questions_str = _format_previous_suggested_questions(
            previous_suggested_questions, chat_history
        )

        prompt = QUIZ_PROMPT if is_quiz else ANSWER_PROMPT
        chain = prompt | llm

        # Build the template variables for this invocation
        if is_quiz:
            prompt_vars = {
                "question": question,
                "context": context,
                "chat_history": history_str,
                "welcome_messages": welcome_str,
                "raw_text": raw_text or "(no raw text available)",
                "page_summaries": page_summaries or "(no page summaries available)",
            }
        else:
            conv_name = conversation_name or "(unnamed conversation)"
            prompt_vars = {
                "question": question,
                "context": context,
                "chat_history": history_str,
                "welcome_messages": welcome_str,
                "matched_pages": matched_pages,
                "chapter_context": chapter_context or "(no chapter structure detected)",
                "exif_metadata": exif_str,
                "previous_suggested_questions": prev_questions_str,
                "conversation_name": conv_name,
                "conversation_id": conversation_id,
            }

        # Render the full prompt string and log it for debugging
        rendered_messages = prompt.format_messages(**prompt_vars)
        rendered_prompt = "\n\n---MSG---\n\n".join(
            f"[{m.type}]\n{m.content}" for m in rendered_messages
        )
        logger.info(
            f"📋 [FULL PROMPT] conversation={conversation_id} length={len(rendered_prompt)} chars"
        )
        logger.info(f"📋 [FULL PROMPT]\n{rendered_prompt}")

        # Send the rendered prompt to Sentry with full text as attachment
        # (breadcrumbs get [Filtered] by data scrubbing, attachments don't)
        with sentry_sdk.push_scope() as scope:
            scope.set_extra("conversation_id", conversation_id)
            scope.set_extra("question", question)
            scope.set_extra("prompt_length", len(rendered_prompt))
            scope.set_extra("mode", "quiz" if is_quiz else "answer")
            scope.add_attachment(
                bytes=rendered_prompt.encode("utf-8"),
                filename=f"prompt_{conversation_id}.txt",
                content_type="text/plain",
            )
            sentry_sdk.capture_message(
                f"LLM prompt for conversation {conversation_id}",
                level="info",
            )

        logger.info(
            f"🔗 Invoking LLM chain (matched_pages={len(matched_pages) if not is_quiz else 'N/A'} chars, exif={len(exif_str) if not is_quiz else 'N/A'} chars)..."
        )
        with sentry_sdk.start_span(op="llm.invoke", name=f"LLM {getattr(llm, 'model', 'unknown')}"):
            ai_message = chain.invoke(prompt_vars)
        answer = ai_message.content

        # Log the full question and model response for observability (visible in GCP Cloud Logging)
        model_name = getattr(llm, "model", None) or getattr(llm, "model_name", None) or "unknown"
        logger.info(f"📝 [Q&A LOG] conversation={conversation_id} model={model_name}")
        logger.info(f"📝 [Q&A LOG] question={question}")
        logger.info(f"📝 [Q&A LOG] answer={answer[:500]}")

        # Log prompt cache metrics if available
        usage = ai_message.response_metadata.get("token_usage") or ai_message.response_metadata.get(
            "usage", {}
        )
        if usage:
            cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            if cached:
                logger.info(
                    f"💾 Prompt cache hit: {cached}/{prompt_tokens} tokens cached ({cached * 100 // prompt_tokens}%)"
                )
            else:
                logger.info(f"💾 Prompt cache miss: 0/{prompt_tokens} tokens cached")
            logger.info(
                f"📊 Token usage: prompt={prompt_tokens} completion={completion_tokens} total={prompt_tokens + completion_tokens}"
            )

            sentry_logger.info(
                "LLM invocation completed for conversation {conversation_id}",
                conversation_id=conversation_id,
                attributes={
                    "model": model_name,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "cached_tokens": cached,
                    "answer_length": len(answer),
                    "chunk_count": len(rows),
                    "is_quiz": is_quiz,
                },
            )

            rag_span.set_data("model", model_name)
            rag_span.set_data("prompt_tokens", prompt_tokens)
            rag_span.set_data("completion_tokens", completion_tokens)
            rag_span.set_data("total_tokens", prompt_tokens + completion_tokens)

        logger.info(f"✅ Generated answer: {answer[:100]}...")

        citations = _build_citations(rows)
        answer = _strip_orphan_source_tags(answer, len(citations))

        return {
            "answer": answer,
            "citations": citations,
        }
