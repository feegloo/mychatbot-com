from __future__ import annotations

import json
import logging
import re

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from .extractors import clean_file_name
from .lang_detect import detect_language

logger = logging.getLogger(__name__)


def _sample_chunks(chunks: list[str], max_chunks: int = 8) -> list[str]:
    """Stratified sampling to capture diverse topics throughout the document."""
    if len(chunks) <= max_chunks:
        return chunks

    indices = set()
    indices.update(range(min(3, len(chunks))))
    mid_start = len(chunks) // 3
    mid_end = 2 * len(chunks) // 3
    step = max(1, (mid_end - mid_start) // 2)
    indices.update(range(mid_start, mid_end, step))
    indices.update(range(max(0, len(chunks) - 3), len(chunks)))
    sorted_indices = sorted(list(indices))[:max_chunks]
    return [chunks[i] for i in sorted_indices]


def suggest_questions_from_chunks(
    chunks: list[str],
    language: str = None,
    description: str = "",
    file_names: list[str] = None,
    file_types: dict[str, str] = None,
    welcome_message: str = "",
) -> list[str]:
    from .rag import get_llm

    sample_chunks = _sample_chunks(chunks)
    sample = "\n\n".join(sample_chunks)[:10000]

    # Detect language if not provided
    if language is None:
        text_for_lang = sample[:2000]
        language = detect_language(text_for_lang)

    # --- Generate 3 natural questions + 2 contextual/creative prompts in one call ---
    # Build file context hints for smarter action suggestions
    _file_types_str = ""
    if file_types and file_names:
        _file_types_str = ", ".join(f"{n} ({file_types.get(n, 'unknown')})" for n in file_names)

    if language == "pl":
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """Wygeneruj DOKŁADNIE 5 sugerowanych promptów dla użytkownika na podstawie poniższej treści.

Odpowiedz WYŁĄCZNIE prawidłowym JSON-em (bez markdown, bez ```json). Format:
{{"questions": ["q1", "q2", "q3", "q4", "q5"]}}

Zasady:
- Pierwsze 3 to naturalne pytania o treść dokumentu (krótkie, konkretne, klikalne) — BEZ emoji
- Jeśli dokument jest autorstwa lub dotyczy znanej osoby (pisarz, naukowiec, polityk, artysta itp.), JEDNO z pierwszych 3 pytań MUSI brzmieć "Kim był [Imię Nazwisko]?" (jeśli osoba nie żyje) lub "Kim jest [Imię Nazwisko]?" (jeśli żyje). Użyj pełnego imienia i nazwiska.
- Ostatnie 2 to kreatywne prompty-akcje sformułowane jako naturalne zdania/polecenia (np. "Stwórz quiz z najważniejszych faktów 🧠", "Napisz wiersz inspirowany treścią 🎭")
  Każdy prompt-akcja MUSI kończyć się odpowiednim emoji
- Często sugeruj akcję generowania obrazu powiązaną z konkretnym tematem dokumentu (np. "Wygeneruj obraz inspirowany [temat/bohater/scena] 🎨") — dopasuj temat do treści, nie używaj ogólnikowego "aktualnego nastroju"
- Każdy prompt powinien być zwięzły (max 10 słów)
- NIE numeruj, NIE dodawaj wyjaśnień
- NIE używaj formatu "temat - akcja" ani nawiasów kwadratowych — pisz naturalne zdania
- KRYTYCZNE: WSZYSTKIE prompty (pytania i akcje) muszą być w 100% w języku treści dokumentu. Jeśli treść jest po francusku, pisz po francusku. Jeśli po niemiecku, pisz po niemiecku. NIGDY nie mieszaj języków. Dotyczy to również nazw akcji.

== OBOWIĄZKOWE AKCJE DLA KONKRETNYCH TYPÓW TREŚCI ==
Te zasady mają NAJWYŻSZY PRIORYTET — jeśli treść pasuje, MUSISZ użyć danej akcji jako jednej z dwóch:

1. POWIEŚĆ / BELETRYSTYKA (kryminał, thriller, romans, fantasy, sci-fi, horror itp.):
   → OBOWIĄZKOWO: "Napisz inspirowany rozdział w stylu [Imię Nazwisko autora] ✏️"
   Przykład: "Napisz inspirowany rozdział w stylu Remigiusza Mroza ✏️"
   Drugą akcję dobierz losowo z poniższej listy (quiz, oś czasu, mapa myśli itp.)

2. POEZJA / FILOZOFIA / CYTATY / AFORYZMY (poeta, filozof, zbiór cytatów):
   → OBOWIĄZKOWO: "Napisz inspirowany wiersz w stylu [Imię Nazwisko autora] 🎭"
   Przykład: "Napisz inspirowany wiersz w stylu Paula Coelho 🎭"
   Drugą akcję dobierz losowo z poniższej listy.

3. PORADNIK / SAMOROZWÓJ / LISTA WSKAZÓWEK / WORKBOOK (produktywność, pewność siebie, nawyki, wskazówki, ćwiczenia, wyzwania, jak zrobić, samodoskonalenie):
   → OBOWIĄZKOWO: Wybierz LOSOWO jeden z poniższych promptów generowania treści inspirowanej:
     - "Napisz 10 nowych wskazówek inspirowanych [Imię Nazwisko autora] 💡"
     - "Stwórz 7 ćwiczeń inspirowanych [Imię Nazwisko autora] 🏋️"
     - "Wygeneruj 12 pytań refleksyjnych inspirowanych [Imię Nazwisko autora] 🤔"
     - "Napisz 5 scenariuszy z życia inspirowanych [Imię Nazwisko autora] 🎭"
     - "Stwórz 14-dniowy plan działania inspirowany [Imię Nazwisko autora] 📅"
   Zamień [Imię Nazwisko autora] na prawdziwe imię i nazwisko autora wykryte z dokumentu. Jeśli autor jest nieznany, użyj "autora" lub opisu np. "tym poradnikiem".
   Drugą akcję dobierz losowo z poniższej listy.

4. Jeśli treść NIE pasuje do powyższych — dobierz obie akcje LOSOWO z poniższej listy.
   NIE zawsze wybieraj quiz — quiz to tylko JEDNA z wielu opcji. Bądź kreatywny i zróżnicowany.

== Wytyczne dotyczące promptów-akcji ==

Wybierz akcje które NAJLEPIEJ pasują do charakteru treści. Bądź kreatywny i kontekstowy:

a) Quiz 🧠 — sugeruj gdy:
   - dokument to długi ebook lub podręcznik
   - PDF wygląda na materiał edukacyjny (wykład, kurs, tutorial)
   - treść uczy jakiegoś tematu z faktami do sprawdzenia

b) Checklista ✅ — sugeruj gdy:
   - treść opisuje kroki do wykonania, procedurę, instrukcję
   - użytkownik powinien "podjąć działanie" na podstawie tekstu
   - dokument zawiera listę wymagań, zadań, rzeczy do zrobienia

c) Napisz inspirowany wiersz 🎭 — sugeruj gdy:
   - autor to poeta, pisarz, lub treść związana z poezją
   - dokument to zbiór cytatów, aforyzmów, wierszy
   - treść ma literacki, artystyczny charakter
   - akcja: "napisz inspirowany wiersz" (nie samo "wiersz")

d) Napisz inspirowany rozdział ✏️ — sugeruj gdy:
   - dokument to fragment powieści, opowiadania, książki beletrystycznej
   - np. książka Stephena Kinga — "napisz inspirowany rozdział w stylu autora"
   - treść ma wyraźny styl narracyjny do naśladowania
   - akcja: "napisz inspirowany rozdział" (nie samo "napisz rozdział")

e) Przepis 🍝 — sugeruj gdy:
   - zdjęcie pokazuje składniki lub gotowe danie
   - plik dotyczy gotowania, pieczenia chleba, przepisów kulinarnych
   - widoczne są produkty spożywcze na zdjęciu

f) Rozpoznaj osobę 🔍 — sugeruj TYLKO gdy:
   - na zdjęciu widać wyraźnie osobę/twarz ludzką
   - NIE sugeruj dla zdjęć krajobrazów, zwierząt, przedmiotów
   - format: "Kto jest kobietą/mężczyzną/osobą na zdjęciu nazwa_pliku? 🔍"

g) Metadane EXIF 📷 — sugeruj TYLKO gdy:
   - plik to zdjęcie (image) — nigdy dla PDF lub tekstu

h) Diagram mermaid 🖼️ — sugeruj gdy:
   - treść opisuje proces, przepływ, architekturę, hierarchię
   - dokument zawiera relacje między elementami do zwizualizowania
   - treść techniczna z komponentami do zobrazowania

i) Tabela porównawcza 📊 — sugeruj gdy:
   - treść porównuje produkty, opcje, cechy, wyniki
   - dokument zawiera dane liczbowe do zestawienia

j) Podsumowanie 📝 — sugeruj gdy:
   - dokument jest bardzo długi (wiele stron)
   - treść jest gęsta, pełna szczegółów do skondensowania

k) Wyjaśnij jak dla dziecka 👶 — sugeruj gdy:
   - treść jest techniczna, naukowa, lub pełna żargonu
   - dokument wymaga uproszczenia dla zrozumienia

l) Fiszki do nauki 🃏 — sugeruj gdy:
   - treść zawiera definicje, terminy, słownictwo, kluczowe pojęcia
   - dokument to materiał do nauki, podręcznik, notatki z wykładu
   - akcja: "stwórz fiszki do nauki" z pytaniem na jednej stronie i odpowiedzią na drugiej

m) Oś czasu / timeline 📅 — sugeruj gdy:
   - treść opisuje wydarzenia historyczne, biografię, kamienie milowe projektu
   - dokument zawiera daty i sekwencję wydarzeń w czasie
   - akcja: "stwórz oś czasu wydarzeń"

n) Mapa myśli 🧩 — sugeruj gdy:
   - treść przedstawia wiele powiązanych koncepcji lub tematów
   - dokument nadaje się do wizualnego przeglądu relacji między ideami
   - akcja: "stwórz mapę myśli" (wygeneruj jako diagram mermaid mindmap)

o) Za i przeciw ⚖️ — sugeruj gdy:
   - treść dotyczy decyzji, recenzji, oceny produktów lub opcji
   - dokument prezentuje argumenty za i przeciw, lub porównuje podejścia
   - akcja: "wypisz za i przeciw"

p) Szkic emaila / listu 📧 — sugeruj gdy:
   - treść zawiera informacje wymagające formalnej komunikacji
   - dokument to reklamacja, wniosek, raport, lub wymaga odpowiedzi
   - akcja: "napisz szkic emaila na podstawie treści"

q) Notatki do nauki 📓 — sugeruj gdy:
   - treść to wykład, artykuł naukowy, rozdział podręcznika
   - dokument jest gęsty i wymaga wyciągnięcia najważniejszych punktów
   - akcja: "stwórz notatki do nauki" (skondensowane, z kluczowymi punktami)

r) Przetłumacz treść 🌍 — sugeruj gdy:
   - treść jest w języku obcym dla użytkownika (np. dokument po angielsku dla polskiego użytkownika)
   - dokument zawiera fragmenty w różnych językach
   - akcja: "przetłumacz na [język]"

s) FAQ / Najczęstsze pytania ❓ — sugeruj gdy:
   - treść to dokumentacja, instrukcja obsługi, regulamin, polityka
   - dokument opisuje produkt, usługę, lub proces z wieloma szczegółami
   - akcja: "stwórz FAQ na podstawie treści"

t) Debata / Argumenty 💬 — sugeruj gdy:
   - treść dotyczy kontrowersyjnego tematu, opinii, eseju argumentacyjnego
   - dokument prezentuje stanowisko które można przedyskutować z wielu stron
   - akcja: "przedstaw argumenty obu stron"

u) Słownik pojęć 📖 — sugeruj gdy:
   - treść zawiera specjalistyczną terminologię, żargon branżowy
   - dokument techniczny, medyczny, prawny z wieloma terminami do wyjaśnienia
   - akcja: "stwórz słownik kluczowych pojęć"

v) List motywacyjny / CV 💼 — sugeruj gdy:
   - treść to oferta pracy, opis stanowiska, wymagania rekrutacyjne
   - dokument to CV, portfolio, lub materiały do aplikacji
   - akcja: "napisz list motywacyjny na podstawie oferty"

w) Plan działania / Roadmap 🚩 — sugeruj gdy:
   - treść opisuje cele, strategię, plan projektu, wizję
   - dokument wymaga przełożenia na konkretne kroki z terminami
   - akcja: "stwórz plan działania krok po kroku"

x) Recenzja / Opinia ⭐ — sugeruj gdy:
   - treść to produkt, książka, film, usługa, restauracja
   - dokument zawiera doświadczenie użytkownika z czymś do oceny
   - akcja: "napisz recenzję" lub "napisz opinię"

y) Post na social media 📱 — sugeruj gdy:
   - treść jest interesująca, newsowa, inspirująca, wizualna
   - dokument nadaje się do podzielenia się z innymi online
   - akcja: "napisz post na LinkedIn/Instagram/Twitter"

z) Streszczenie wykonawcze 🎯 — sugeruj gdy:
   - treść to długi raport, analiza, biznesplan, badanie
   - dokument wymaga krótkiego, decyzyjnego streszczenia dla zarządu
   - akcja: "stwórz streszczenie wykonawcze (executive summary)"

aa) Scenariusz rozmowy / Dialog 🎬 — sugeruj gdy:
   - treść dotyczy wywiadu, przesłuchania, spotkania, negocjacji
   - dokument ma potencjał dramaturgiczny lub edukacyjny w formie dialogu
   - akcja: "napisz scenariusz rozmowy / dialog"

ab) Infografika (tekstowa) 📊 — sugeruj gdy:
   - treść zawiera statystyki, dane liczbowe, fakty do zwizualizowania
   - dokument nadaje się do prezentacji kluczowych liczb i faktów
   - akcja: "stwórz tekstową infografikę z najważniejszymi danymi"

ac) Piosenka / Tekst muzyczny 🎵 — sugeruj gdy:
   - treść jest emocjonalna, opowiada historię, ma rymowany charakter
   - dokument dotyczy muzyki, tekstów piosenek, lub ma potencjał liryczny
   - akcja: "napisz inspirowaną piosenkę / tekst muzyczny"

ad) Prezentacja / Slajdy 📽️ — sugeruj gdy:
   - treść wymaga zaprezentowania publiczności, wykład, raport
   - dokument ma strukturę nadającą się na slajdy (sekcje, punkty)
   - akcja: "stwórz zarys prezentacji (outline slajdów)"

ae) Bajka / Opowiadanie dla dzieci 🧚 — sugeruj gdy:
   - treść zawiera moralne lekcje, przygody, postacie fantastyczne
   - dokument lub zdjęcie przedstawia zwierzęta, naturę, magiczne sceny
   - akcja: "napisz bajkę inspirowaną treścią"

af) Wygeneruj obraz 🎨 — sugeruj gdy:
   - treść opisuje sceny, krajobrazy, postacie, przedmioty wizualne
   - zdjęcie lub dokument ma potencjał do wizualnej reinterpretacji
   - użytkownik może chcieć zobaczyć artystyczną wizualizację treści
   - akcja: MUSI zawierać dokładnie frazy "wygeneruj obraz" lub "generate image" w treści
   - akcja MUSI nawiązywać do konkretnego tematu/sceny/bohatera dokumentu (np. "Wygeneruj obraz: mroczny las z Joanną Chyłką 🎨") — NIE używaj ogólnikowego "aktualnego nastroju"

ag) Postaw diagnozę / diagnoza 🔬 — sugeruj gdy:
   - dokument to wyniki badań laboratoryjnych, badania krwi, panel tarczycowy, lipidogram
   - treść zawiera wartości takie jak: morfologia, hemoglobina, leukocyty, cholesterol, glukoza, TSH, FT3, FT4, ferrytyna, witamina D, witamina B12, homocysteina, magnez, żelazo, CRP, D-dimery, kreatynina, bilirubina, ALAT, ASPAT, HbA1c, kwas foliowy, estradiol, testosteron itp.
   - plik wygląda jak sprawozdanie z badań z laboratorium (ALAB, Diagnostyka, Synevo itp.)
   - akcja: "Postaw diagnozę na podstawie wyników 🔬"
   - UWAGA: to ma WYSOKI PRIORYTET — jeśli treść to wyniki badań, ta akcja MUSI być jedną z dwóch

ah) Napisz nowe wskazówki 💡 — sugeruj gdy:
   - dokument to poradnik, lista wskazówek, "N sposobów na...", "X wskazówek jak..."
   - treść to samorozwój, produktywność, pewność siebie, nawyki, motywacja
   - akcja: "Napisz 10 nowych wskazówek inspirowanych [Imię Nazwisko autora] 💡"

ai) Stwórz ćwiczenia 🏋️ — sugeruj gdy:
   - dokument to workbook, materiał kursowy, przewodnik po ćwiczeniach, zbiór zadań
   - treść zawiera kroki do wykonania lub praktyczne elementy do ćwiczenia
   - akcja: "Stwórz 7 ćwiczeń inspirowanych [Imię Nazwisko autora] 🏋️"

aj) Wygeneruj pytania refleksyjne 🤔 — sugeruj gdy:
   - dokument jest introspekcyjny, dotyczący journalingu, coachingu, mindset, samorozwoju
   - treść skłania do autorefleksji lub głębszego myślenia
   - akcja: "Wygeneruj 12 pytań refleksyjnych inspirowanych [Imię Nazwisko autora] 🤔"

ak) Scenariusze z życia 🎭 — sugeruj gdy:
   - dokument stosuje zasady do rzeczywistych sytuacji, zawiera case study, przykłady
   - treść dotyczy umiejętności społecznych, komunikacji, przywództwa, psychologii
   - akcja: "Napisz 5 scenariuszy z życia inspirowanych [Imię Nazwisko autora] 🎭"

al) 14-dniowy plan działania 📅 — sugeruj gdy:
   - dokument to przewodnik po samodoskonaleniu, wyzwanie lub ustrukturyzowany program
   - treść można przełożyć na codzienne zadania praktyczne
   - akcja: "Stwórz 14-dniowy plan działania inspirowany [Imię Nazwisko autora] 📅"

Przesłane pliki: {file_types_str}
Opis dokumentu: {description}""",
                ),
                ("human", "{content}"),
            ]
        )
    else:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """Generate EXACTLY 5 suggested prompts for the user based on the following uploaded content.

Reply with ONLY valid JSON (no markdown, no ```json). Format:
{{"questions": ["q1", "q2", "q3", "q4", "q5"]}}

Rules:
- First 3 are natural questions about the document content (short, specific, clickable) — NO emoji
- If the document is by or about a well-known person (author, scientist, politician, artist, etc.), ONE of the first 3 questions MUST be "Who was [Full Name]?" (if deceased) or "Who is [Full Name]?" (if alive). Use the person's full name.
- Last 2 are creative action-prompts phrased as natural sentences/commands (e.g., "Create a quiz from the key facts 🧠", "Write a poem inspired by this 🎭")
  Each action-prompt MUST end with a relevant emoji
- Frequently suggest a subject-specific image generation action tied to the document's concrete topic/character/scene (e.g. "Generate image: dark forest with Hermione 🎨") — do NOT use the generic phrase "current mood"; make it relevant to what the document is actually about
- Each prompt should be concise (max 10 words)
- Do NOT number, do NOT add explanations
- Do NOT use "topic - action" format or square brackets — write natural sentences
- CRITICAL: ALL prompts (questions AND actions) MUST be written 100% in the language of the document content. If the content is in French, write everything in French. If in German, write in German. NEVER mix languages. This applies to action labels, topics, and everything else.

== MANDATORY ACTIONS FOR SPECIFIC CONTENT TYPES ==
These rules have the HIGHEST PRIORITY — if the content matches, you MUST use that action as one of the two:

1. NOVEL / FICTION (crime, thriller, romance, fantasy, sci-fi, horror, etc.):
   → MANDATORY: "Write inspired chapter like [Author Full Name] ✏️"
   Example: "Write inspired chapter like Stephen King ✏️"
   Pick the second action RANDOMLY from the list below (quiz, timeline, mind map, etc.)

2. POETRY / PHILOSOPHY / QUOTES / APHORISMS (poet, philosopher, quote collection):
   → MANDATORY: "Write inspired poem like [Author Full Name] 🎭"
   Example: "Write inspired poem like Paulo Coelho 🎭"
   Pick the second action RANDOMLY from the list below.

3. NON-FICTION GUIDE / SELF-HELP / TIPS LIST / WORKBOOK (productivity, confidence, habits, how-to, advice, personal growth, exercises, challenges):
   → MANDATORY: Pick ONE of the following inspired generation prompts AT RANDOM:
     - "Write 10 new tips inspired by [Author Full Name] 💡"
     - "Create 7 exercises inspired by [Author Full Name] 🏋️"
     - "Generate 12 reflection questions inspired by [Author Full Name] 🤔"
     - "Draft 5 real-life scenarios inspired by [Author Full Name] 🎭"
     - "Build a 14-day action plan inspired by [Author Full Name] 📅"
   Replace [Author Full Name] with the actual author's name detected from the document. If no author is found, use "the author" or a short description like "this guide".
   Pick the second action RANDOMLY from the list below.

4. If the content does NOT match any of the above — pick BOTH actions RANDOMLY from the list below.
   Do NOT always pick quiz — quiz is just ONE of many options. Be creative and varied.

== Action Prompt Guidelines ==

Pick actions that BEST fit the nature of the content. Be creative and contextual:

a) Quiz 🧠 — suggest when:
   - document is a long ebook or textbook
   - PDF looks like educational material (lecture, course, tutorial)
   - content teaches a subject with facts worth testing

b) Checklist ✅ — suggest when:
   - content describes steps to follow, a procedure, instructions
   - user should "take action" based on the text
   - document contains requirements, tasks, things to do

c) Write inspired poem 🎭 — suggest when:
   - author is a poet, writer, or content relates to poetry
   - document is a collection of quotes, aphorisms, poems
   - content has a literary, artistic character
   - e.g. a Paolo Coelho book — "write inspired poem in the author's style"
   - action: "write inspired poem" (not just "poem")

d) Write inspired chapter ✏️ — suggest when:
   - document is a fragment of a novel, short story, fiction book
   - e.g. a Stephen King book — "write inspired chapter in the author's style"
   - content has a distinct narrative style worth imitating
   - action: "write inspired chapter" (not just "write chapter")

e) Recipe 🍝 — suggest when:
   - image shows ingredients or a finished dish
   - file is about cooking, baking bread, culinary recipes
   - food products are visible in the photo

f) Recognize person 🔍 — suggest ONLY when:
   - image clearly shows a person/human face
   - do NOT suggest for landscapes, animals, objects
   - format: "Who is the woman/man/person in filename? 🔍"

g) EXIF metadata 📷 — suggest ONLY when:
   - file is an image (photo) — never for PDF or text files

h) Mermaid diagram 🖼️ — suggest when:
   - content describes a process, flow, architecture, hierarchy
   - document has relationships between elements to visualize
   - technical content with components to diagram

i) Comparison table 📊 — suggest when:
   - content compares products, options, features, results
   - document contains numerical data to tabulate

j) Summary 📝 — suggest when:
   - document is very long (many pages)
   - content is dense, full of details to condense

k) Explain like I'm 5 👶 — suggest when:
   - content is technical, scientific, or full of jargon
   - document needs simplification for understanding

l) Flashcards 🃏 — suggest when:
   - content contains definitions, terms, vocabulary, key concepts
   - document is study material, textbook, lecture notes
   - action: "create study flashcards" with question on one side, answer on the other

m) Timeline 📅 — suggest when:
   - content describes historical events, biography, project milestones
   - document contains dates and a sequence of events over time
   - action: "create timeline of events"

n) Mind map 🧩 — suggest when:
   - content presents many related concepts or topics
   - document is suitable for a visual overview of relationships between ideas
   - action: "create mind map" (generate as mermaid mindmap diagram)

o) Pros & Cons ⚖️ — suggest when:
   - content is about decisions, reviews, product evaluations, or options
   - document presents arguments for and against, or compares approaches
   - action: "list pros and cons"

p) Email / letter draft 📧 — suggest when:
   - content contains info requiring formal communication
   - document is a complaint, application, report, or needs a response
   - action: "draft an email based on the content"

q) Study notes 📓 — suggest when:
   - content is a lecture, scientific article, textbook chapter
   - document is dense and needs key points extracted
   - action: "create study notes" (condensed, with key takeaways)

r) Translate content 🌍 — suggest when:
   - content is in a foreign language for the user
   - document contains passages in different languages
   - action: "translate to [language]"

s) FAQ / Frequently asked questions ❓ — suggest when:
   - content is documentation, user manual, terms of service, policy
   - document describes a product, service, or process with many details
   - action: "create FAQ from the content"

t) Debate / Arguments 💬 — suggest when:
   - content covers a controversial topic, opinion piece, argumentative essay
   - document presents a position that can be discussed from multiple sides
   - action: "present arguments from both sides"

u) Glossary 📖 — suggest when:
   - content contains specialized terminology, industry jargon
   - technical, medical, or legal document with many terms to explain
   - action: "create a glossary of key terms"

v) Cover letter / CV 💼 — suggest when:
   - content is a job offer, position description, recruitment requirements
   - document is a CV, portfolio, or application materials
   - action: "write a cover letter based on the job offer"

w) Action plan / Roadmap 🚩 — suggest when:
   - content describes goals, strategy, project plan, vision
   - document needs to be translated into concrete steps with deadlines
   - action: "create a step-by-step action plan"

x) Review / Opinion ⭐ — suggest when:
   - content is a product, book, film, service, restaurant
   - document contains a user experience with something to evaluate
   - action: "write a review" or "write an opinion"

y) Social media post 📱 — suggest when:
   - content is interesting, newsworthy, inspiring, visual
   - document is suitable for sharing online with others
   - action: "write a LinkedIn/Instagram/Twitter post"

z) Executive summary 🎯 — suggest when:
   - content is a long report, analysis, business plan, research
   - document needs a short, decision-oriented summary for management
   - action: "create an executive summary"

aa) Dialogue / Script 🎬 — suggest when:
   - content is about an interview, hearing, meeting, negotiation
   - document has dramatic or educational potential in dialogue form
   - action: "write a dialogue / script"

ab) Text infographic 📊 — suggest when:
   - content contains statistics, numerical data, facts to visualize
   - document is suitable for presenting key numbers and facts
   - action: "create a text infographic with the most important data"

ac) Song / Lyrics 🎵 — suggest when:
   - content is emotional, tells a story, has a rhyming character
   - document is about music, song lyrics, or has lyrical potential
   - action: "write an inspired song / lyrics"

ad) Presentation / Slides 📽️ — suggest when:
   - content needs to be presented to an audience, lecture, report
   - document has a structure suitable for slides (sections, bullet points)
   - action: "create a presentation outline (slide outline)"

ae) Fairy tale / Children's story 🧚 — suggest when:
   - content contains moral lessons, adventures, fantastical characters
   - document or photo shows animals, nature, magical scenes
   - action: "write a fairy tale inspired by the content"

af) Generate image 🎨 — suggest when:
   - content describes scenes, landscapes, characters, visual objects
   - photo or document has potential for visual reinterpretation
   - user might want to see an artistic visualization of the content
   - action: MUST contain exactly the phrase "generate image" in the label
   - action MUST reference the document's specific subject, character, or scene (e.g. "Generate image: stormy sea at sunset 🎨") — do NOT use the generic phrase "current mood"; tailor it to the actual content

ag) Make a diagnosis 🔬 — suggest when:
   - document is lab test results, blood tests, thyroid panel, lipid panel
   - content contains values like: CBC, hemoglobin, WBC, cholesterol, glucose, TSH, FT3, FT4, ferritin, vitamin D, vitamin B12, homocysteine, magnesium, iron, CRP, D-dimers, creatinine, bilirubin, ALT, AST, HbA1c, folic acid, estradiol, testosterone, etc.
   - file looks like a laboratory report
   - action: "Make a diagnosis based on results 🔬"
   - NOTE: this has HIGH PRIORITY — if the content is lab results, this action MUST be one of the two

ah) Write new tips 💡 — suggest when:
   - document is a tips guide, advice collection, "X ways to...", "N tips for..."
   - content is non-fiction self-help, productivity, confidence, habit-building, motivation
   - action: "Write 10 new tips inspired by [Author Full Name] 💡"

ai) Create exercises 🏋️ — suggest when:
   - document is a workbook, course material, practice guide, or exercise collection
   - content has step-by-step tasks or actionable practice elements
   - action: "Create 7 exercises inspired by [Author Full Name] 🏋️"

aj) Generate reflection questions 🤔 — suggest when:
   - document is introspective, journaling, self-coaching, mindset, or personal growth focused
   - content prompts self-examination or deeper thinking about one's life/habits
   - action: "Generate 12 reflection questions inspired by [Author Full Name] 🤔"

ak) Real-life scenarios 🎭 — suggest when:
   - document applies principles to real situations, contains case studies, or practical examples
   - content is about social skills, communication, leadership, or psychology
   - action: "Draft 5 real-life scenarios inspired by [Author Full Name] 🎭"

al) 14-day action plan 📅 — suggest when:
   - document is a self-improvement guide, challenge program, or structured practice plan
   - content can be translated into day-by-day practice tasks with clear goals
   - action: "Build a 14-day action plan inspired by [Author Full Name] 📅"

Uploaded files: {file_types_str}
Document description: {description}""",
                ),
                ("human", "{content}"),
            ]
        )

    llm = get_llm()
    chain = prompt | llm | StrOutputParser()
    response = chain.invoke(
        {"content": sample, "description": description, "file_types_str": _file_types_str}
    )

    # Parse JSON response
    try:
        parsed = json.loads(response.strip())
        questions = parsed.get("questions", [])
        if isinstance(questions, list) and len(questions) >= 3:
            return _append_contextual_prompts(
                questions[:5], file_names, file_types, language, welcome_message, description
            )
    except (json.JSONDecodeError, AttributeError):
        logger.warning(
            "Failed to parse JSON from suggested questions response, falling back to line parsing"
        )

    # Fallback: parse as lines (backward compat)
    questions = [line.strip("- ").strip() for line in response.splitlines() if line.strip()]
    return _append_contextual_prompts(
        questions[:5], file_names, file_types, language, welcome_message, description
    )


_PERSON_PATTERN = re.compile(
    r"\b(person|people|man|woman|portrait|face|selfie|human|"
    r"osoba|osoby|mężczyzna|kobieta|twarz|portret|człowiek|ludzie|"
    r"depicts? a|shows? a|presents? a|przedstawia)\b",
    re.IGNORECASE,
)

_WOMAN_PATTERN = re.compile(
    r"\b(woman|girl|female|lady|kobieta|dziewczyna|pani)\b",
    re.IGNORECASE,
)

_MAN_PATTERN = re.compile(
    r"\b(man|boy|male|gentleman|mężczyzna|chłopak|pan)\b",
    re.IGNORECASE,
)

_INGREDIENT_PATTERN = re.compile(
    r"\b(ingredient|ingredients|składnik|składniki|skład|composition|"
    r"contains|zawiera|nutrition|wartości odżywcze|product label|etykiet)\b",
    re.IGNORECASE,
)

_LAB_TEST_PATTERN = re.compile(
    r"\b(morfologia|hemoglobina|leukocyty|erytrocyty|hematokryt|płytki krwi|"
    r"cholesterol|triglicerydy|glukoza|kreatynina|bilirubina|ferrytyna|"
    r"witamina D|witamina B12|25\(OH\)D|TSH|FT3|FT4|ATPO|ATG|homocysteina|"
    r"kwas foliowy|magnez w surowicy|żelazo w surowicy|CRP|D-dimery|"
    r"estradiol|testosteron|insulina|HbA1c|ALAT|ASPAT|GGT|mocznik|"
    r"blood count|CBC|hemoglobin|WBC|RBC|hematocrit|platelet|"
    r"vitamin D|vitamin B12|folic acid|ferritin|creatinine|bilirubin|"
    r"triglyceride|glucose|magnesium|iron.*serum|thyroid|cortisol|"
    r"lab.{0,5}result|blood.{0,5}test|wynik.{0,5}bada[nń]|sprawozdanie z bada[nń]|"
    r"zakres referencyjny|reference range|laboratorium|laboratory)\b",
    re.IGNORECASE,
)


def _extract_subject_phrase(
    welcome_message: str,
    description: str,
    file_names: list[str] | None,
    language: str | None,
) -> str:
    """Return a short subject phrase derived from the document context.

    Priority order:
    1. Markdown h1/h2 heading from welcome_message, then description
    2. First substantive (non-heading) line from welcome_message, then description,
       truncated to ≤45 chars
    3. Clean file name of first uploaded file
    4. Generic fallback

    Headings up to 50 chars are returned as-is; longer headings are truncated.
    """
    texts = [t.strip() for t in (welcome_message, description) if t and t.strip()]

    # 1. Heading: ## Title or # Title
    for text in texts:
        heading_match = re.search(r"^#{1,2}\s+(.+)", text, re.MULTILINE)
        if heading_match:
            phrase = heading_match.group(1).strip()
            # Strip bold markers sometimes present in headings
            phrase = re.sub(r"\*\*(.+?)\*\*", r"\1", phrase)
            if 3 <= len(phrase) <= 50:
                return phrase
            if len(phrase) > 50:
                return phrase[:47].rstrip() + "..."

    # 2. First non-empty, non-heading line
    for text in texts:
        lines = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
        if lines:
            candidate = lines[0]
            # Drop leading bold/italic markers
            candidate = re.sub(r"^\*{1,3}(.+?)\*{1,3}", r"\1", candidate)
            if len(candidate) > 45:
                candidate = candidate[:42].rstrip() + "..."
            if len(candidate) >= 4:
                return candidate

    # 3. File name fallback
    if file_names:
        return clean_file_name(file_names[0])[:45]

    # 4. Generic
    return "tej treści" if language == "pl" else "this content"


def _append_contextual_prompts(
    questions: list[str],
    file_names: list[str] | None,
    file_types: dict[str, str] | None,
    language: str | None,
    welcome_message: str = "",
    description: str = "",
) -> list[str]:
    """Build final list: 3 normal questions + up to 2 action prompts = max 5.

    Contextual action prompts (EXIF, recognize, file metadata) take priority
    over LLM-generated action prompts. 'recognize person name' is only added when
    the welcome message indicates a person is visible in the image.
    'create recipe' is added when the welcome message mentions ingredients.
    """
    # Split LLM output: first 3 are questions, rest are actions
    normal_questions = questions[:3]
    llm_actions = questions[3:5]

    subject = _extract_subject_phrase(welcome_message, description, file_names, language)
    pinned_image_prompt = (
        f"Wygeneruj obraz inspirowany: {subject} 🎨"
        if language == "pl"
        else f"Generate image inspired by: {subject} 🎨"
    )

    # Build contextual action prompts (higher priority than LLM actions)
    contextual: list[str] = []
    has_lab_tests = bool(_LAB_TEST_PATTERN.search(welcome_message))
    if file_names and file_types:
        has_person = bool(_PERSON_PATTERN.search(welcome_message))
        is_woman = bool(_WOMAN_PATTERN.search(welcome_message))
        is_man = bool(_MAN_PATTERN.search(welcome_message))
        has_ingredients = bool(_INGREDIENT_PATTERN.search(welcome_message))

        for name in file_names:
            if len(contextual) >= 2:
                break
            ftype = file_types.get(name, "document")
            display_name = clean_file_name(name)
            short_name = display_name if len(display_name) <= 30 else display_name[:27] + "..."

            if ftype == "image":
                if has_ingredients and len(contextual) < 2:
                    if language == "pl":
                        contextual.append(f"Stwórz przepis na podstawie {short_name} 🍝")
                    else:
                        contextual.append(f"Create a recipe from {short_name} 🍝")
                if len(contextual) < 2:
                    if language == "pl":
                        contextual.append(f"Pokaż metadane EXIF dla {short_name} 📷")
                        if has_person and len(contextual) < 2:
                            if is_woman:
                                contextual.append(f"Kto jest kobietą na zdjęciu {short_name}? 🔍")
                            elif is_man:
                                contextual.append(f"Kto jest mężczyzną na zdjęciu {short_name}? 🔍")
                            else:
                                contextual.append(f"Kto jest osobą na zdjęciu {short_name}? 🔍")
                    else:
                        contextual.append(f"Show EXIF metadata for {short_name} 📷")
                        if has_person and len(contextual) < 2:
                            if is_woman:
                                contextual.append(f"Who is the woman in {short_name}? 🔍")
                            elif is_man:
                                contextual.append(f"Who is the man in {short_name}? 🔍")
                            else:
                                contextual.append(f"Who is the person in {short_name}? 🔍")
            # PDF metadata prompt removed — LLM-generated creative actions are more valuable

    # Lab test / blood test results → diagnosis prompt (highest priority)
    if has_lab_tests and len(contextual) < 2:
        if language == "pl":
            contextual.insert(0, "Postaw diagnozę na podstawie wyników 🔬")
        else:
            contextual.insert(0, "Make a diagnosis based on results 🔬")

    # The pinned image prompt takes one of the two action slots.
    # The second action slot goes to a contextual prompt (higher priority) or an LLM action.
    second_action = (contextual + llm_actions)[:1]
    actions = [pinned_image_prompt] + second_action

    # Build the final list: 3 questions + 2 action slots = exactly 5 (or fewer if inputs short)
    final = normal_questions + actions

    deduped: list[str] = []
    seen: set[str] = set()
    for question in final:
        key = question.strip().lower()
        if key and key not in seen:
            deduped.append(question)
            seen.add(key)
        if len(deduped) >= 5:
            break

    return deduped
