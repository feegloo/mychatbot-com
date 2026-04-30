"""Shared `[action:Label]` button rules used by BOTH:

- assistant answers (shared.rag.ANSWER_PROMPT), and
- welcome-message suggested prompts (shared.suggested_questions, shared.describe- weThis is the single source of truth for how the LLM must format, - welcome-message suhe 7 action buttons. Keep wording verbatim across consumers.

See `PROMPTS_REFACTOR.md` for the migration plan.
"""

from .action_content_types import ACTION_CONTENT_TYPES_EN

_LABELS_ACTIONS_TEMPLATE = r"""d) Action Buttons:
- Output follow-up suggestions as action markers: [action:Label]. Place them at the very end of your answer, after all content.
- **NO INTRO PHRASE BEFORE ACTION BUTTONS — CRITICAL**: Do NOT write any lead-in sentence immediately before the action buttons. The following patterns are STRICTLY FORBIDDEN:
  * "Jeśli chcesz, mogę teraz napisać:" / "If you'd like, I can now write:"
  * "Możesz też zapytać:" / "You could also ask:"
  * "Oto kilka kierunków:" / "Here are a few directions:"
  * "Jeśli chcesz, mogę:" / "If you want, I can:"
  * "Chcesz, żebym:" / "Would you like me to:"
  * Any sentence of the form "I can [do X], [do Y], or [do Z]" followed by the buttons
  The action button labels are self-explanatory — they need no announcement or offer. Writing such a phrase is redundant and weakens the response.
  * EXCEPTION — a very short natural bridge is acceptable ONLY when ALL of these conditions hold: (1) the answer is long and substantive (multiple paragraphs), (2) the bridge genuinely adds something the answer didn't already express, (3) it is preceded by a markdown horizontal rule `---` on its own line. Even then, use it very rarely — the vast majority of answers should end with no bridge at all.
    STRICTLY FORBIDDEN bridge phrases (never write these, regardless of answer length):
    - "A few deeper angles to explore"
    - "A few other angles you could explore"
    - "Here are some angles to explore"
    - "A few angles worth exploring"
    - "A few directions you could take next"
    - Any variant of the above using "angles", "directions", "deeper", "explore", "further"
    These are the most overused, hollow-sounding fillers — they add zero value and must never appear.
    ACCEPTABLE sparse bridges (use at most once in 30–40 answers, never twice in the row (if previous answer had a bridge) only after a long substantive response, always preceded by `---` on its own line):

    **Generic bridges** (safe for any long response):
    - "Some threads worth pulling"
    - "Where to go from here"
    - "Kilka kierunków do eksploracji"
    - "Możliwe ścieżki dalej"

    **Contextual mood-matching bridges** — use after creative, poetic, or emotionally resonant responses (poems, fiction, imagery, tender scenes, philosophical pieces) when the qualifying word genuinely MIRRORS the dominant register of the answer. Use at most once in 6–8 creative responses — sparingly, because even good bridges can start to feel formulaic if overused. Always preceded by `---` on its own line.
    - After a tender/gentle poem or scene: "Some softer directions to explore"
    - After a melancholic or reflective piece: "Quieter threads to follow"
    - After something playful or whimsical: "A few lighter angles"
    - After something intense or dramatic: "Some sharper threads to pull"
    - After a philosophical or meditative response: "A few deeper threads"
    - After something wistful or nostalgic: "Some lingering directions"
    - Polish equivalents (match the tone):
      - "Kilka łagodniejszych kierunków" (tender/soft)
      - "Cichsze wątki do eksploracji" (quiet/melancholic)
      - "Kilka lżejszych ścieżek" (playful/light)
      - "Głębsze wątki do eksploracji" (philosophical/meditative)
    - **Principle**: the adjective (softer, quieter, lighter, sharper, deeper, lingering) should feel earned — it should echo the specific quality of THIS answer, not a generic description of what the buttons are. When no quality clearly fits, use a generic bridge or skip the bridge entirely.

  * BAD: "Jeśli chcesz, mogę teraz napisać:\n\nostrzejszą, bardziej buntowniczą wersję,\nkrótszy manifest w 10 zdaniach,\nalbo wersję jeszcze bliższą tonowi całej Jednego i jego własności.\n[action:...] ..."
  * BAD: "If you'd like, I can: write a sharper version, summarize in 10 sentences, or go deeper into a specific chapter.\n[action:...] ..."
  * GOOD (no intro at all — the MOST COMMON case): answer text ends naturally, then a blank line, then the action line immediately.
  * GOOD (rare bridge, only after a long response): "---\n\nSome threads worth pulling\n\n[action:...] ..."
  * GOOD (rare bridge, Polish, only after a long response): "---\n\nKilka kierunków do eksploracji\n\n[action:...] ..."
  * GOOD (mood-matching bridge after a tender poem): "---\n\nSome softer directions to explore\n\n[action:...] ..."
  * GOOD (mood-matching bridge, Polish, after a reflective piece): "---\n\nCichsze wątki do eksploracji\n\n[action:...] ..."
- ALWAYS generate EXACTLY 7 follow-up action buttons after your answer.
- CRITICAL FORMAT: All 7 action markers MUST be placed on a SINGLE line, space-separated, like this:
  [action:Label1] [action:Label2] [action:Label3] [action:Label4] [action:Label5] [action:Label6] [action:Label7]
- NEVER place each action marker on its own line — they must all be together on one line with no newlines between them.
- CRITICAL — EXACT KEY FORMAT: The marker key is ALWAYS lowercase `action` followed immediately by a colon, with NO number, NO space, and NO bracket before the colon. The ONLY valid format is `[action:Label]`.
  * FORBIDDEN formats (all produce unparsable output):
    - `[Action 1: Label]` — wrong: uppercase, numbered, space before colon
    - `[Action 2: Label]` — wrong: uppercase, numbered, space before colon
    - `[Action: Label]` — wrong: space after colon (label must start immediately after `:`)
    - `[action : Label]` — wrong: space before colon
    - `[Action:Label]` — wrong: uppercase first letter
  * ONLY valid format: `[action:Label]` — lowercase `action`, colon, no space, label text directly.
- **LANGUAGE MIRRORING — CRITICAL, NON-NEGOTIABLE**: Every single [action:...] label — ALL 7 of them, including rich action-prompts with emoji — MUST be written in the EXACT SAME language as the user's latest question and your answer. This is the #1 rule for action buttons. Do NOT mix languages. Do NOT default to English "just because the action type (quiz / checklist / comparison table / generate image) is often phrased in English in examples". The examples in this prompt happen to be mostly in English for illustration only — they are NOT a template to copy verbatim. You MUST translate every action label into the answer's language.
  * IMPORTANT: translate ONLY the text INSIDE the marker. The marker key is fixed English and MUST stay `[action:...]` in every language.
  * Good (Polish label, correct key): `[action:Stwórz tabelę porównawczą 📊]`
  * Bad (translated key): `[akcja:Stwórz tabelę porównawczą 📊]`
  * If the user asked in Polish and you answered in Polish → ALL 7 labels in Polish (yes, even "Stwórz tabelę porównawczą 📊", "Lista kontrolna ✅", "Wygeneruj obraz inspirowany: … 🎨" — never "Create comparison table", "Make a checklist", "Generate image inspired by …").
  * If the user asked in English and you answered in English → ALL 7 labels in English.
  * Same rule applies to German → German, Spanish → Spanish, French → French, Ukrainian → Ukrainian, Arabic → Arabic, etc. Match the answer's language exactly.
  * Before emitting the final line of 7 [action:...] buttons, RE-READ each label and confirm it is in the same language as your answer above. If any label drifted into English (or another language), rewrite it.
  * Example — user asks in Polish "Który kod wybrać do spożywki?", answer is in Polish → ALL labels in Polish:
    `[action:Który kod wybrać między 7 i 8?] [action:Czy kod 2 też nadaje się do spożywki?] [action:Stwórz tabelę porównawczą kodów higienicznych 📊] [action:Stwórz checklistę doboru higienicznego ✅] [action:Dlaczego gładsza powierzchnia ułatwia czyszczenie? 🧽] [action:Podsumuj najlepsze opcje do kontaktu z żywnością 📋] [action:Wygeneruj obraz inspirowany: porównanie wykończeń Tri Clamp dla food-grade 🎨]`
  * Reversed example — user asks the SAME thing in English "Which code should I choose for food contact?", answer is in English → ALL labels in English:
    `[action:Which code to choose between 7 and 8?] [action:Is code 2 also suitable for food contact?] [action:Create comparison table of hygienic finish codes 📊] [action:Make a hygienic selection checklist ✅] [action:Why does smoother surface help cleaning? 🧽] [action:Summarize the best food-grade options 📋] [action:Generate image inspired by: comparison of food-grade Tri Clamp finishes 🎨]`
- IMPORTANT: The 7 buttons MUST follow this layout pattern:
  * **Positions 1–2** (plain follow-up questions, NO emoji): two sharp follow-up questions about the topic.
  * **Position 3 — FIRST visible rich slot (the eye-catching one)**: the only rich action the user sees inline. Positions 4–7 collapse into a "More ..." dropdown. This slot should go to whichever rich action has the HIGHEST visualization value for THIS answer — the one that most vividly "shows" what the response is about. Often that is a "Generate image …" action, but not always (see the priority + relevance rules below).
  * **Positions 4–7 (inside "More ..." overflow)**: the remaining rich action-prompts (quiz, checklist, diagram, summary, comparison table, timeline, mind map, wisdom quote, creative chapter, image generation when not placed at position 3, etc.). Each MUST end with a relevant emoji.
  * Every rich action (positions 3–7) MUST end with a relevant emoji; plain follow-ups (positions 1–2) must NOT have a trailing emoji.
- **"More ..." CONCEPT — what the user sees and how they invoke it**:
  * The UI splits your 7 buttons into VISIBLE (positions 1–3, rendered as pills) and OVERFLOW (positions 4–7, hidden under a clickable "More ..." pill). Same pattern applies to welcome-message suggestions (visible 1–5, overflow 6–10).
  * That means positions 4–7 are the "surprise / deeper cut" tier. Put the less obvious but still valuable branches there — do NOT waste them on weak or duplicate ideas just because they are out of sight.
  * The literal string "More ..." is ALSO a user command. If the user's message is exactly "More ...", "More...", "More", "Więcej", "Więcej ...", or any clear request for "more suggestions / more actions / more ideas / give me more options / show more", treat it as a request to produce a FRESH batch of 7 NEW action buttons. In that case:
      - Do NOT answer a fictional question and do NOT repeat anything from Section 5c (previously shown suggestions).
      - Write ONE short sentence acknowledging the request (e.g. "Here are seven more directions to explore ..."), then output exactly 7 NEW [action:...] buttons on a single line, following the same layout rules (positions 1–2 plain questions, 3 first-visible rich action, 4–7 deeper overflow).
      - Push deeper / wider / more surprising than the previous set: zoom in on specific names, scenes, numbers from the conversation; try angles the user has not yet explored.
  * The same concept applies when the user clicks a "More ..." item in welcome suggestions — treat each such click like any other question: answer it normally and append a new set of 7 action buttons.
- If the user explicitly asks for richer/more colorful output, prefer a rich action label in this style: "Create more colorful version … 🎨" (or Polish equivalent), still respecting all other button rules.
- IMAGE-GENERATION TRIGGER — 🎨 is RESERVED EXCLUSIVELY for image-generation actions. The frontend routes any message containing 🎨 (or the English phrases "generate image", "create image", "new image") to the /generate-image API.
  * Every image-generation action label MUST end with 🎨 — this is the sole, canonical trigger.
  * For readability the label SHOULD also contain the phrase "generate image" (English) or "wygeneruj obraz" (Polish), but 🎨 alone is sufficient to trigger the API. The label MUST additionally contain the word "inspired" / "inspirowany" — see the PLACEMENT & PROMPT FORMAT section below for why.
  * NEVER attach 🎨 to any non-image action — doing so would misroute the click to the image API.

- **RICH-ACTION PRIORITY — ORDER vs. CONTEXT (two rules, both apply)**:
  The rich slots (positions 3–7) are chosen by combining a baseline priority order with context fit. Higher-priority actions are preferred, BUT a lower-priority action can (and should) leapfrog ahead when it fits the current answer much better. Think of each button as a distinct BRANCH of the answer — pick the "action tool" that best VISUALIZES or EXTENDS that specific branch.

  Baseline priority order (a = highest, then b, c, …). Use this ONLY as the starting preference; relevance to the current answer, conversation history, and document type always overrides raw order:
  a) **Generate image 🎨** — visualize a scene, character, concept, diagram, or schema (placement rule in the next bullet).
  b) **Write inspired chapter / page / scene ✏️** — for fiction, novels, strong narrative voices. Use the real author name.
  c) **Write inspired poem / verse / aphorism 📜** — for poetry, philosophy, quotes, aphorism collections.
  d) **Wisdom quote 💡** ("złota myśl") — for authors famous for aphorisms (Einstein, Seneca, Wilde, Lao Tzu, …) or any quote-heavy source.
  e) **Diagnosis / clinical analysis 🔬** — ONLY for genuine lab results / clinical documents.
  f) **Quiz 🧠** — for ebooks, textbooks, language-learning material, study content.
  g) **Checklist ✅ / action plan 🚩 / next-steps 📋** — for problem documents, how-tos, procedures.
  h) **Timeline 📅** — for biographies, historical events, project milestones.
  i) **Mermaid diagram / schema 🖼️** or **mind map 🧩** — for processes, hierarchies, interconnected concepts.
  j) **Comparison table 📊 / pros & cons ⚖️ / glossary 📖** — for structured, comparative, or terminology-heavy content.
  k) **Summary 📝 / study notes 📓 / flashcards 🃏 / FAQ ❓ / presentation 📽️ / executive summary 🎯** — for long, dense, or educational material.
  l) **Creative variants — song 🎵, dialogue 🎬, fairy tale 🧚, children's story, social post 📱, review ⭐, infographic 📊, recipe 🍝, email draft 📧, cover letter 💼** — pick when the content genuinely matches.

  How to apply:
  1. **Start from order** — give earlier letters first claim on the slots.
  2. **Let context override** — if an item from (e.g.) letter (h) is the most resonant extension of THIS specific answer, promote it above higher-priority items that fit less well.
  3. **Each button = one branch of the answer** — pick the action TOOL that best visualizes/extends that branch (image for visual branches, diagram for structural branches, timeline for temporal branches, checklist for actionable branches, creative-writing for stylistic branches, etc.). Do not default every branch to the same tool.
  4. Do not force an item that does not fit — skip it and move to the next priority. A factual medical doc should never get "write inspired chapter"; a novel rarely needs a comparison table.

- **FACTUAL DOCUMENTS — RELEVANCE, NOT LOCKDOWN**:
  For factual, professional, or scientific documents (lab results, medical reports, legal contracts, financial statements, scientific papers, technical specs, business reports, journalistic articles, etc.), the 2 plain follow-up questions (positions 1–2) and the majority of rich actions SHOULD stay grounded in the document's domain and serve a domain expert (doctor / lawyer / engineer / analyst).
  * Rich actions like results tables, checklists, timelines, glossaries, FAQs, next-steps plans, quizzes, and comparison charts are all welcome.
  * Image generation IS allowed for factual docs when there is a genuinely useful visualization — a diagram of the anatomy/system being discussed, a concept illustration, a visual metaphor for the finding, a chart-style scene, an infographic-like illustration. Pick visuals that reinforce understanding rather than entertainment reframings.
  * Still avoid obvious style-drift failures: do not turn medical results into detective stories, do not invent fictional characters unrelated to the content, do not reframe serious documents as genre parody. A bad example for blood results would be "Wygeneruj obraz: pieróg-detektyw z lupą 🎨"; a good visualization would be "Wygeneruj obraz inspirowany: schemat działania tarczycy w organizmie 🎨" or "Generate image inspired by: conceptual illustration of cardiovascular risk factors 🎨".
  * Use taste — a medical results doc still shouldn't get a "write inspired chapter" button, but it can absolutely get a meaningful image.

- **"generate image" encouragement — PLACEMENT & PROMPT FORMAT**:
  Image generation is one of the most valuable rich actions because it turns the answer into something SHOWABLE. Include it in ALMOST EVERY answer that has any visualizable angle — but its POSITION (3 vs. inside "More ...") depends on context:

  * **Placement rule — roughly 50 / 50, decided by RELEVANCE + USER HISTORY, not by a fixed slot**:
    - ~50% of the time place image generation at **position 3** (the first visible rich slot, the eye-catching one).
    - ~50% of the time place it somewhere in **positions 4–7** (inside the "More ..." overflow) and let a different rich action take position 3.
    - This ratio is a loose guideline, not a strict quota — decide per answer.
    - **Promote to position 3 when** any of these hold:
      · the answer describes a concrete scene, portrait, landscape, object, mood, or visual metaphor that clearly benefits from visualization;
      · the last 1–2 user/assistant messages are themselves visual, narrative, or imagery-heavy (a recent scene deserves a picture);
      · the conversation history (Section 5b) shows the user has ALREADY triggered 🎨 / image generation in this conversation — they clearly enjoy it, lean into it;
      · a diagram / schema / conceptual illustration would add real explanatory value (factual, medical, technical content);
      · the source is heavily visual (novel with strong imagery, children's book, poem with strong scene-building, art-related content).
    - **Demote to "More ..." (positions 4–7) when**:
      · a different rich action is OBVIOUSLY more valuable for this specific answer (e.g. lab results → diagnosis at 3; language-learning question → quiz at 3; procedural document → checklist at 3; biography question → timeline at 3; novel chapter just discussed → inspired chapter at 3);
      · the answer is purely abstract / analytical with no strong visual hook and nothing compelling to picture;
      · the user has so far shown no interest in visualization and a different tool serves the branch better.
    - When image goes to "More ...", STILL include it — just not as position 3. Only fully omit it when there is genuinely nothing worth picturing.

  * **Prompt format (clear, concrete, reusable) — label MUST include the word "inspired"**:
    - The literal word "inspired" (English) or "inspirowany"/"inspirowana" (Polish) MUST appear in EVERY image-generation label. This is non-negotiable: OpenAI's content filter frequently blocks verbatim copyrighted character/scene prompts (e.g. "Daenerys in the Great Pyramid") but accepts the same prompt reframed as "inspired by …". Labels WITHOUT "inspired" will cause blocked generations.
    - English: `Generate image inspired by: [SUBJECT], [OPTIONAL MOOD / SETTING / STYLE] 🎨`
    - Polish:  `Wygeneruj obraz inspirowany: [TEMAT], [OPCJONALNY NASTRÓJ / SCENERIA / STYL] 🎨`
    - Short vivid variants are fine as long as "inspired" is present: `Generate inspired image: Raskolnikov in the candlelit garret, rain on the window 🎨`.
    - [SUBJECT] MUST be concrete and specific — a named character, a named scene, a specific object, a named concept, a specific diagram type. Never generic ("the book", "current mood", "the topic").
    - Optional trailing details make the image better: who, where, lighting, atmosphere, art style, diagram type.
    - Keep the whole label under ~12 words. Label MUST end with 🎨.

  * **WHAT to visualize — match the image to the branch it represents**:
    1. **The current scene** just described in your answer (a battle, a landscape, a character portrait, a key moment, an object, a mood).
    2. **A thread from the conversation history** — if the user has been building a narrative across several exchanges, visualize the arc (e.g. `Generate image inspired by the journey so far: [scene] 🎨` / `Wygeneruj obraz inspirowany dotychczasową historią: [scena] 🎨`).
    3. **The central concept or emotion** of the answer when no concrete scene exists (e.g. `Generate image inspired by: the loneliness of exile 🎨`).
    4. **A diagram, schema, or conceptual illustration** for factual / scientific / medical / technical content (e.g. `Generate inspired image: schematic of the thyroid feedback loop 🎨` / `Wygeneruj obraz inspirowany: schemat działania leku w organizmie 🎨`). For factual docs, prefer this angle — it adds real explanatory value rather than entertainment reframing.

  * **Bad vs. good prompts**:
    - BAD (missing "inspired"): `Generate image: Daenerys in the Great Pyramid 🎨` — will likely be blocked by OpenAI content filter.
    - BAD (generic / vague): `Generate image of the book 🎨`, `Wygeneruj obraz aktualnego nastroju 🎨`, `Generate image: one folktale in different regional costumes 🎨`.
    - GOOD (specific scene): `Generate image inspired by: Raskolnikov in the candlelit garret, rain on the window 🎨`.
    - GOOD (specific character + setting): `Wygeneruj obraz inspirowany: Chyłka w sądowym korytarzu, kontrowe światło 🎨`.
    - GOOD (diagram / schema): `Generate inspired image: schematic of the thyroid feedback loop 🎨`.
    - GOOD (conversation arc): `Generate image inspired by the journey so far: the Fellowship's path from Shire to Mordor 🎨`.

- **CRITICAL — if the user's request contains 🎨 anywhere, or the phrases "generate image", "create image", "new image", "make image", "draw image" (or combinations like "generate 🎨", "new 🎨"), or Polish phrases like "wygeneruj obraz" (with or without emoji), or any clear intent to produce an image**: DO NOT respond with instructions, prompt examples, or suggestions. Instead respond very briefly — one short sentence about what image you will generate (e.g. "Generating an image of Rumi meditating by candlelight...") — and nothing else. The image generation happens automatically; your text is just an acknowledgment. Do not add action buttons in this case.
- **"creative writing" encouragement for literary content**: If the uploaded document is a novel, fiction, or has a strong narrative voice (thriller, horror, fantasy, romance, crime, sci-fi, etc.), one action button SHOULD suggest writing creative text in the author's style. Use the ACTUAL author name — never use placeholder brackets like [Author]. Vary the phrasing naturally (do not always say "Write inspired chapter like"):
  * For novels/fiction — vary among: "Write inspired chapter like NAME ✏️", "Create a page in NAME's style ✏️", "Improvise a scene like NAME ✏️", "Write a new chapter inspired by NAME ✏️", "Create opening lines in NAME's voice ✏️"
  * For poetry/philosophy/quotes — vary among: "Write inspired poem like NAME 📜", "Compose a verse in NAME's spirit 📜", "Create a poem in NAME's voice 📜", "Write a new aphorism like NAME 📜", "Write inspired quote like NAME 💬"
  * The creative writing button should describe WHAT to write (chapter, scene, page, verse, poem) and reference the real author name — the user should be able to click it and immediately understand what they will get.
  * Prioritize these creative writing actions for literary content — they should appear alongside the image generation action.
  * Do not apply creative fiction writing actions to factual documents (medical, legal, financial, scientific) — those should get domain-appropriate rich actions instead (but image generation IS still welcome there; see above).

- **"złota myśl" (wisdom quote) encouragement**: When source material contains aphorisms, quotes, maxims, or philosophical statements — OR when the author/thinker is well-known for memorable one-liners (e.g. Einstein, Seneca, Marcus Aurelius, Lao Tzu, Oscar Wilde, Nietzsche, Confucius, Buddha, Epictetus, Pascal, Voltaire) — suggest generating a brand-new wisdom quote inspired by the source:
  * **TOP-LEVEL (one of the first 3 buttons, visible without "More...")**: Use this placement when the source IS primarily quotes/aphorisms, or the person is famous for their wit and wisdom. Examples: a collection of Einstein quotes, Stoic philosophy, Tao Te Ching, Oscar Wilde's wit. The "złota myśl" button should be immediately discoverable here.
  * **In "More..." (positions 4–7)**: Use this placement for general authors/writers who have some notable quotes but are not primarily known for aphorisms (e.g. a novelist who occasionally writes beautifully). Hide it in the overflow menu.
  * Label format (MUST stay under 10 words): Use the ACTUAL author name — never placeholder brackets. Polish: "Wygeneruj złotą myśl w stylu NAME 💡". English: "Generate wisdom quote in NAME's voice 💡".
  * When this action is triggered, generate ONE original sentence of wisdom — pithy, resonant, memorable — that captures the author's worldview, voice, and philosophy, as if they wrote it themselves. It should feel like a genuine "złota myśl": timeless, quotable, thought-provoking. NOT a summary or paraphrase of a real quote — a newly invented one in the same spirit.
  * Examples of good "złote myśli" output style:
    - (Einstein-style) "Imagination is the universe folding itself into a mind small enough to wonder." 💡
    - (Seneca-style) "The man who fears tomorrow has already lost today." 💡
    - (Wilde-style) "A cynic is merely a romantic who ran out of patience." 💡
    - (Lao Tzu-style) "The river does not ask permission to reach the sea." 💡
    - (Marcus Aurelius-style) "Strength is not the absence of fear, but the refusal to let it choose your path." 💡
  * **THEME DIVERSITY — MANDATORY for repeated or follow-up quote requests**: When "Write a quote", "Write another quote", or any quote/wisdom-quote action is triggered, you MUST ensure the quote explores a theme NOT already covered in this conversation.
    Step 1 — Audit: Scan the full chat history and identify all themes used in previously generated quotes (e.g. love, patience, grief, haste, longing).
    Step 2 — Select a fresh theme: Choose a theme from a DIFFERENT domain of the author's work. Do NOT default to the theme that best matches the top-ranked retrieved chunks — semantic search clusters around the previous query's topic and will pull similar passages. Override this bias deliberately.
    Step 3 — Write from that theme: Generate the new quote rooted in the selected theme, drawing on the author's voice and philosophy — even if the retrieved source passages are about something else. You are writing an original "in the spirit of" quote, not paraphrasing a source passage.
    - For Shakespeare, the full thematic range includes (but is not limited to): honor, ambition, jealousy, revenge, justice, fate vs. free will, appearance vs. reality, death & immortality, friendship, power & corruption, mercy, nature, madness, time, loyalty, war, forgiveness, pride, duty.
    - For any other author: similarly map out their thematic universe beyond the one theme the RAG chunks happen to surface.
    - Each successive quote must feel like it comes from a **different room** of the author's mind. If previous quotes explored love and impatience, the next should explore justice, or mortality, or ambition — something genuinely new.
    - Use the Welcome Page Description, Chapter Context, and full Chat History as a map of the whole work's themes — not just the top-matching retrieved pages.

- BREVITY — SMART INSIGHT LABELS (CRITICAL):
  * Each label should be aimed at 3–5 words, sometimes for 5–6. Never exceed 10 words.
  * Write them as a "smart insight" — a sharp, specific angle that reveals something non-obvious.
  * Think of them as clickbait-free headlines: short, precise, intriguing.
  * BAD (vague/generic): "What are the main themes in this document?"
  * BAD (rephrased obvious): "How does the composition create balance?"
  * GOOD (smart insight): "Why does asymmetry feel stable here?"
  * GOOD (sharp angle): "Hidden tension in the color palette?"
  * GOOD (unexpected connection): "How lighting contradicts the pose?"
  * Each word must earn its place — cut filler words like "about", "regarding", "in terms of".

- **BRANCHES, NOT SEQUELS**: The 7 action buttons are BRANCHES from your response — diverging directions the conversation could fork into. Think of it as a choose-your-own-adventure: deeper, wider, sideways. Each button should open a DISTINCT path, not variations of the same path.
  * One might go DEEPER into a specific detail mentioned in your answer (zoom in)
  * One might go WIDER to connect the topic to something broader or unexpected (zoom out)
  * One might go SIDEWAYS into a creative, practical, or provocative angle (surprise)
  * Reference specific names, facts, numbers, or quotes from YOUR response to make buttons feel connected and concrete — e.g. if you mentioned **Kordian**, a button could be "Kordian's hidden motive in chapter 4?"
  * But not every button needs a proper name — sometimes a sharp conceptual angle is better: "Why silence matters more than words here?"
  * Push the conversation DEEPER into expert territory. Think like a curious expert who wants to uncover non-obvious insights, counter-intuitive connections, or practical "insider knowledge" hidden in the content.
  * Go beyond surface-level summaries — ask about underlying mechanisms, edge cases, trade-offs, historical context, or real-world implications.
  * Prefer "why" and "how" questions over "what" questions. Prefer questions that reveal hidden patterns, surprising contrasts, or actionable takeaways.
  * NEVER rephrase or rehash information already covered in the current answer or previous conversation. Each suggestion must open a genuinely NEW angle — not a synonym or restatement.

- **WIKI FLOWCHART GRAPH NAVIGATION — BRANCH FROM CONNECTED NODES**:
  Section 3a (Internal Knowledge Wiki) contains a `## Mermaid Flowchart` that encodes relationships between the key concepts/entities in this document as a directed graph. Use this graph to SELECT the plain follow-up questions (positions 1–2 and deeper content branches in positions 4–7):

  **Step-by-step algorithm**:
  1. **Map the question to graph nodes**: Identify which flowchart node(s) most closely match the user's current question — the node whose label best describes what was just asked about. Call this the "anchor node".
  2. **Collect adjacent nodes**: From the anchor node, collect all nodes it connects TO (outgoing edges `==>`, `-->`, `-.->`) and all nodes that connect TO it (incoming edges). These are the "branch candidates".
  3. **Exclude already-explored nodes**: Scan Section 5b (full chat history) for topics already discussed. Remove any branch candidate whose concept was already the subject of a previous question or answer exchange.
  4. **Pick 1–2 branch candidates** for positions 1–2 (the plain follow-up questions): Choose the adjacent nodes with the STRONGEST edge weight (prefer `==>` over `-->` over `-.->`) that have NOT been explored yet. Frame them as sharp "why" or "how" questions about that adjacent concept and its relationship to the anchor.
  5. **Avoid loops**: Never suggest returning to a concept that was the anchor in a previous exchange. The user is navigating the graph — help them move FORWARD through it, not circle back.

  **Why this matters**: Semantic search clusters around the last query's embedding, which pulls adjacent chunks about the SAME concept. The flowchart graph gives you a structural map that semantic similarity can't provide — it shows what is ADJACENT but DIFFERENT. Following edges in the graph guarantees the next question genuinely moves to a new part of the document's concept space.

  **Example** (wiki has: `Encoder ==>|+0.88| CrossAttn`, `CrossAttn -->|+0.77| Decoder`, user asked about Encoder):
  - Anchor = Encoder node
  - Adjacent candidates = CrossAttn (outgoing, strong), Decoder (2 hops)
  - Position 1: "How does cross-attention bridge encoder and decoder?"  ← direct edge from anchor
  - Position 2: "What makes masked self-attention different from cross-attention?"  ← the next hop

  **Example** (wiki has: `NDA <---> ObaStrony`, `Wynagrodzenie ===> IP`, user asked about NDA):
  - Anchor = NDA node  
  - Adjacent candidates = ObaStrony (bidirectional), Kara (from NDA), Wynagrodzenie (separate cluster)
  - Position 1: "What triggers the 50k PLN NDA penalty in practice?"  ← outgoing NDA edge
  - Position 2: "Does the IP clause interact with NDA breach timing?"  ← cross-cluster connection

  **Fallback**: If the wiki is empty, the question maps to no flowchart node, or all adjacent nodes are already explored — fall back to the standard BRANCHES rule above and generate fresh topical questions.



- PREVIOUS SUGGESTIONS: SECTION 5c below lists ALL previously shown suggested prompts grouped by the Q&A exchange they followed. Study the full list carefully. You MUST NOT repeat, rephrase, or closely mirror ANY of them. Generate fresh, progressively deeper questions that explore territory none of the previous prompts touched.

- Example — general knowledge topic, image at position 3 (strong visual scene): [action:What were Socrates' main teachings?] [action:How did Socrates influence Plato?] [action:Generate image inspired by: Socrates debating in the agora at dusk 🎨] [action:Create a Socrates quiz 🧠] [action:Draft a Socratic dialogue 🎬] [action:Build a timeline of his life 📅] [action:Create a mind map of ideas 🧩]
- Example — wisdom/quotes source, e.g. Einstein quotes collection (wisdom quote promoted to position 3, image demoted to "More ..."): [action:How did Einstein view religion and science?] [action:Why did he resist quantum randomness?] [action:Generate wisdom quote in Einstein's voice 💡] [action:Create an Einstein quiz 🧠] [action:Generate image: Einstein at his blackboard, chalk dust in lamplight 🎨] [action:Draft Einstein's letter to a young physicist ✏️] [action:Build a timeline of his breakthroughs 📅]
- Example — novelist, e.g. Dostoevsky "Crime and Punishment" (image at position 3, creative-writing at position 4 — strong scene + strong voice): [action:Why does Raskolnikov justify the murder?] [action:How does guilt evolve through the novel?] [action:Generate image: Raskolnikov in the candlelit garret, rain on the window 🎨] [action:Write chapter in Dostoevsky's style ✏️] [action:Create a character comparison table 📊] [action:Build a crime & punishment timeline 📅] [action:Wygeneruj złotą myśl w stylu Dostojewskiego 💡]
- Example — lab results / diagnosis document (diagnosis promoted to position 3, image demoted into "More ..." as a schematic): [action:Which markers are most concerning here?] [action:What follow-up tests make sense?] [action:Make a diagnosis based on the results 🔬] [action:Create a results summary table 📊] [action:Checklist of next-step actions ✅] [action:Generate image: schematic of the thyroid feedback loop 🎨] [action:Build a timeline of supplementation plan 📅]
- Example — language-learning textbook (quiz promoted to position 3, image demoted): [action:Which tense rule is trickiest here?] [action:How does word order shift in questions?] [action:Create a grammar quiz 🧠] [action:Create flashcards from this chapter 🃏] [action:Generate image: classroom scene illustrating this grammar rule 🎨] [action:Build a 14-day study plan 📅] [action:Create a mind map of verb conjugations 🧩]
- Example — conversation with rich history where user has already triggered image generation earlier (image at position 3, visualizes the ARC so far): [action:What drove Frodo's final choice at Mount Doom?] [action:How did Sam's role evolve across the trilogy?] [action:Generate image summing up the journey so far: the Fellowship's path from Shire to Mordor 🎨] [action:Write chapter in Tolkien's style ✏️] [action:Create a character comparison table 📊] [action:Build a timeline of the Ring's travels 📅] [action:Create a mind map of the story's themes 🧩]

<<CONTENT_TYPES>>"""
LABELS_ACTIONS_RULES = _LABELS_ACTIONS_TEMPLATE.replace(
    "<<CONTENT_TYPES>>", ACTION_CONTENT_TYPES_EN
)

# ---------------------------------------------------------------------------
# Quiz-specific action rules
# Embedded into QUIZ_PROMPT by quiz.py (same <<placeholder>> pattern as
# LABELS_ACTIONS_RULES is embedded into ANSWER_PROMPT in rag.py).
# ---------------------------------------------------------------------------
QUIZ_ACTIONS_RULES = """After the [quiz:...] block, output exactly 7 [action:...] buttons on a SINGLE line, space-separated. These let the user keep exploring via more quizzes or other rich actions.

QUIZ RESPONSE — action button layout:

- **Positions 1–3** (rendered as visible pills in the UI): Three different follow-up QUIZ suggestions. Look at the document content and invent three alternative quizzes on DIFFERENT aspects than the one you just generated. Each label must end with 🧠.
  * Position 1: Quiz on a different SUBTOPIC, chapter, or section of the same document.
  * Position 2: Quiz in a different FORMAT — e.g. if you generated single-choice, suggest a multiple-choice variant; or suggest a true/false quiz, an open-ended scenario quiz, or a fill-in-the-blank style.
  * Position 3: Quiz focused on a specific concept, character, event, or detail from the document that was NOT yet covered.

- **Positions 4–7** ("More ..." overflow, hidden behind a "More ..." pill): Four rich actions that are NOT quiz. Choose from the standard rich-action priority list — whichever 4 best EXTEND or VISUALIZE the document content:
  image 🎨 · flashcards 🃏 · study notes 📓 · timeline 📅 · checklist ✅ · comparison table 📊 · mind map 🧩 · summary 📝 · inspired chapter ✏️ · poem 📜 · wisdom quote 💡 · FAQ ❓ · presentation 📽️ · …
  Image generation 🎨 is strongly recommended whenever there is a visualizable scene, concept, or diagram — include the word "inspired" in the label and end with 🎨.

CRITICAL FORMAT RULES:
- ALL 7 [action:...] markers on ONE single line, space-separated. NEVER put each on its own line.
- LANGUAGE MIRRORING — NON-NEGOTIABLE: Every label in the EXACT SAME language as the quiz. Polish quiz → Polish labels. English quiz → English labels. No mixing.
- All 7 positions use emoji (quiz buttons end with 🧠; other rich actions end with their relevant emoji).
- NEVER attach 🎨 to a non-image action — 🎨 routes the click to the image-generation API.
- Do NOT wrap the line of buttons in any Markdown heading or bullet.

Examples:

English quiz (history textbook):
[action:Quiz: causes of WWI 🧠] [action:Multiple-choice quiz on key battles 🧠] [action:True/false quiz on leaders and treaties 🧠] [action:Create study flashcards 🃏] [action:Generate image inspired by: a WWI trench at dawn, barbed wire and fog 🎨] [action:Build a WWI timeline 📅] [action:Summarize key themes 📝]

Polish quiz (novel):
[action:Quiz z innego rozdziału 🧠] [action:Quiz wielokrotnego wyboru o postaciach 🧠] [action:Quiz prawda/fałsz z fabuły 🧠] [action:Stwórz fiszki do nauki 🃏] [action:Wygeneruj obraz inspirowany: kluczowa scena powieści 🎨] [action:Napisz rozdział w stylu autora ✏️] [action:Zbuduj oś czasu wydarzeń 📅]"""
