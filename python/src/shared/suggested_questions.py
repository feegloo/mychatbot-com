from __future__ import annotations

import json
import logging
import random
import re

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from .extractors import clean_file_name
from .lang_detect import detect_language
from .languages import LANG_NAMES as _LANG_NAMES
from .llm_instrument import traced_llm_call

logger = logging.getLogger(__name__)
MAX_TOTAL_SUGGESTED_PROMPTS = 10
MAX_NORMAL_QUESTIONS = 3
MAX_ACTION_PROMPTS = 7

# Regex to extract the document language emitted by the model as [language]xx[/language].
_DOC_LANGUAGE_TAG_RE = re.compile(r'\[language\]([a-z]{2,5})\[/language\]', re.IGNORECASE)

# Polish locative forms ("po X") for the most common languages used in dialogues.
_LANG_PL_LOCATIVE: dict[str, str] = {
    "en": "angielsku", "pl": "polsku", "de": "niemiecku", "fr": "francusku",
    "es": "hiszpańsku", "it": "włosku", "ru": "rosyjsku", "uk": "ukraińsku",
    "pt": "portugalsku", "nl": "niderlandzku", "cs": "czesku", "sk": "słowacku",
    "ja": "japońsku", "zh": "chińsku", "ko": "koreańsku",
}


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
    page_count: int | None = None,
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
                    """Wygeneruj do 10 sugerowanych promptów dla użytkownika na podstawie poniższej treści.
Domyślnie zwracaj pełne 10; mniej tylko gdy treść jest zbyt uboga, by tworzyć sensowne, różne propozycje.

Odpowiedz WYŁĄCZNIE prawidłowym JSON-em (bez markdown, bez ```json). Format:
{{"questions": ["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8", "q9", "q10"]}}

Zasady:
- Pierwsze 3 to naturalne pytania o treść dokumentu (krótkie, konkretne, klikalne) — BEZ emoji
- KRYTYCZNE: Pytania formułuj jako intencję użytkownika — NIE jako pytanie modelu do użytkownika. Zamiast "Chcesz X?" pisz po prostu "X". NIGDY nie używaj zwrotów "Chcesz…?", "Czy chcesz…?", "Czy mogę…?", "Powinienem…?". Przykłady: ❌ "Chcesz krótki opis finału bez spoilerów?" → ✅ "Krótki opis finału bez spoilerów". ❌ "Chcesz pełne streszczenie procesu Szlezyngierów?" → ✅ "Pełne streszczenie procesu Szlezyngierów".
- Jeśli dokument jest autorstwa lub dotyczy znanej osoby (pisarz, naukowiec, polityk, artysta itp.), JEDNO z pierwszych 3 pytań MUSI brzmieć "Kim był [Imię Nazwisko]?" (jeśli osoba nie żyje) lub "Kim jest [Imię Nazwisko]?" (jeśli żyje). Użyj pełnego imienia i nazwiska.
- Kolejne (do 7) to kreatywne prompty-akcje sformułowane jako naturalne zdania/polecenia (np. "Stwórz quiz z najważniejszych faktów 🧠", "Napisz nowy wiersz inspirowany treścią 📜")
  Każdy prompt-akcja MUSI kończyć się odpowiednim emoji
- Często sugeruj akcję generowania obrazu powiązaną z konkretnym tematem dokumentu (np. "Wygeneruj obraz inspirowany [temat/bohater/scena] 🎨") — dopasuj temat do treści, nie używaj ogólnikowego "aktualnego nastroju"
- KRYTYCZNE: emoji 🎨 jest ZAREZERWOWANE WYŁĄCZNIE dla akcji generowania obrazu. Nigdy nie dodawaj 🎨 do innej akcji. Każda akcja generowania obrazu MUSI kończyć się 🎨 — to 🎨 (a nie konkretne słowa) uruchamia API generowania obrazu. Dla czytelności akcja powinna też zawierać frazę "wygeneruj obraz".
- KRYTYCZNE: emoji ✅ jest ZAREZERWOWANE WYŁĄCZNIE dla akcji tworzenia list kontrolnych/checklist (np. "Stwórz checklistę wymaganych kroków ✅"). NIGDY nie używaj ✅ jako ogólnego "zatwierdzone", "poprawione", "ulepszone" ani żadnego innego znaczenia. Przykłady zabronionych użyć: ❌ "Wyostrz opis pod rekrutera ✅" (użyj 🎯 lub 💪), ❌ "Dopracuj CV ✅" (użyj ✏️ lub 💼). Emoji ✅ (a nie słowa) uruchamia interfejs checklista — błędne użycie psuje UI.
- KRYTYCZNE: emoji ☝️ jest ZAREZERWOWANE WYŁĄCZNIE dla akcji "lista kluczowych faktów" (np. "Napisz listę kluczowych faktów ☝️"). NIGDY nie używaj ☝️ jako zwykłego wskazania czy akcentowania. Emoji ☝️ (a nie konkretne słowa) uruchamia tryb listy kluczowych faktów. Gdy generujesz akcję ☝️ jako kontynuację odpowiedzi o konkretnym temacie, ZAWSZE umieść temat w etykiecie. ŹLE: `Lista głównych składników ☝️`. DOBRZE: `Lista głównych składników Transformera ☝️`.
- KRYTYCZNE: akcje tłumaczenia treści MUSZĄ kończyć się flagą docelowego języka, NIE globusem 🌍. Przykłady: "Przetłumacz na angielski 🇬🇧", "Przetłumacz na polski 🇵🇱", "Przetłumacz na niemiecki 🇩🇪", "Przetłumacz na francuski 🇫🇷". Użyj flagi kraju, w którym mówi się docelowym językiem.
- Każdy prompt powinien być zwięzły (max 10 słów)
- NIE numeruj, NIE dodawaj wyjaśnień
- NIE używaj formatu "temat - akcja" ani nawiasów kwadratowych — pisz naturalne zdania
- KRYTYCZNE: WSZYSTKIE prompty (pytania i akcje) muszą być w 100% po polsku. NIGDY nie mieszaj języków. Dotyczy to również nazw akcji.

== UKŁAD UI "More ..." (KRYTYCZNE — zrozum jak Twoje wyjście jest pokazywane) ==
10 promptów, które zwracasz, jest dzielonych w UI:
  * Pozycje 1-5 są OD RAZU WIDOCZNE jako klikalne pigułki pod wiadomością powitalną (pierwsze wrażenie).
  * Pozycje 6-10 zwijają się do menu rozwijanego "More ..." (mniej ważne / niespodzianki / niszowe).
Czyli pozycje 1-3 (trzy naturalne pytania) plus pozycje 4-5 (pierwsze DWIE akcje) to to, co użytkownik faktycznie widzi najpierw. Najbardziej atrakcyjne, najlepiej dopasowane do dokumentu akcje ZAWSZE idą na pozycje 4 i 5. Reszta trafia do "More ...".

== OBOWIĄZKOWE POZYCJE 4 i 5 DLA KSIĄŻEK / DZIEŁ Z AUTOREM ==
Jeśli dokument to książka, powieść, ebook, zbiór poezji, filozofia — lub dowolne dzieło z wyraźnym autorem — PIERWSZE DWIE akcje (pozycje 4 i 5, czyli widoczne) MUSZĄ brzmieć:
  * Pozycja 4 — akcja twórcza w stylu autora, dobrana do gatunku:
     - Powieść / beletrystyka: "Napisz nowy inspirowany rozdział w stylu [Imię Nazwisko autora] ✏️"
     - Poezja / aforyzmy: "Napisz nowy inspirowany wiersz w stylu [Imię Nazwisko autora] 📜"
     - Cykl / długa saga: "Napisz inspirowaną książkę w stylu [Imię Nazwisko autora] 📖"
     - Poradnik / samorozwój: jeden z wariantów inspirowanego generowania (wskazówki 💡, ćwiczenia 🏋️, pytania refleksyjne 🤔, scenariusze 🎭, plan 14-dniowy 📅)
  * Pozycja 5 — DRUGI obraz, ale BARDZIEJ SZCZEGÓŁOWY niż przypięty obraz (który już odwołuje się do tytułu). Użyj kluczowego pojęcia, motywu, ikonicznej sceny lub głównego bohatera zamiast samego tytułu:
     - "Wygeneruj obraz inspirowany [konkretne pojęcie/scena/postać] 🎨"
Pozostałe akcje (quiz, oś czasu, mapa myśli, złota myśl, tabela porównawcza, fiszki itd.) idą na pozycje 6-10 pod "More ...".
Wyjątki:
  * Dokumenty problemowe (pisma urzędowe, wezwania, wyniki badań, dokumenty prawne/administracyjne) — NIE stosuj tej reguły; pozostaw pozycje 4-5 domenowe (diagnoza, checklista, plan działania itd.).
  * Zdjęcia / obrazy bez wyraźnego autora — zastąp pozycję 4 akcją EXIF / rozpoznaj osobę / przepis (jeśli pasuje); pozycja 5 zostaje jako obraz inspirowany tematem zdjęcia.

== OBOWIĄZKOWE AKCJE DLA KONKRETNYCH TYPÓW TREŚCI ==
Te zasady mają NAJWYŻSZY PRIORYTET — jeśli treść pasuje, MUSISZ użyć danej akcji wśród promptów-akcji:

1. POWIEŚĆ / BELETRYSTYKA (kryminał, thriller, romans, fantasy, sci-fi, horror itp.):
   → OBOWIĄZKOWO pozycja 4: "Napisz nowy inspirowany rozdział w stylu [Imię Nazwisko autora] ✏️"
   → OBOWIĄZKOWO pozycja 5: DRUGI obraz — ale MUSI być BARDZIEJ SZCZEGÓŁOWY niż przypięty obraz (który już odwołuje się do tytułu książki). Użyj KLUCZOWEGO POJĘCIA, GŁÓWNEGO MOTYWU, IKONICZNEJ SCENY lub GŁÓWNEGO BOHATERA zamiast samego tytułu.
   Przypięty obraz zawsze odwołuje się do tytułu książki, więc pozycja 5 powinna wejść głębiej: wybierz najbardziej wyrazisty, pamiętny lub tematycznie bogaty element dokumentu.
   Format: "Wygeneruj obraz inspirowany [konkretne pojęcie/scena/postać] 🎨"
   Przykładowe pary (pozycja 4 + pozycja 5):
   • "Napisz nowy inspirowany rozdział w stylu George'a R. R. Martina ✏️" + "Wygeneruj obraz inspirowany Czerwonym Weselem 🎨"
   • "Napisz nowy inspirowany rozdział w stylu George'a R. R. Martina ✏️" + "Wygeneruj obraz inspirowany Żelaznym Tronem 🎨"
   • "Napisz nowy inspirowany rozdział w stylu Remigiusza Mroza ✏️" + "Wygeneruj obraz inspirowany mrocznym śledztwem i tajemnicą 🎨"
   • "Napisz nowy inspirowany rozdział w stylu Stephena Kinga ✏️" + "Wygeneruj obraz inspirowany nawiedzonym hotelem Overlook 🎨"
   • "Napisz nowy inspirowany rozdział w stylu J. R. R. Tolkiena ✏️" + "Wygeneruj obraz inspirowany Jedynym Pierścieniem i Górą Przeznaczenia 🎨"
   • "Napisz nowy inspirowany rozdział w stylu J. K. Rowling ✏️" + "Wygeneruj obraz inspirowany Turniejem Trójmagicznym 🎨"
   • "Napisz nowy inspirowany rozdział w stylu Dana Browna ✏️" + "Wygeneruj obraz inspirowany tajemnicą Świętego Graala 🎨"
   • "Napisz nowy inspirowany rozdział w stylu Agathy Christie ✏️" + "Wygeneruj obraz inspirowany sceną morderstwa w Orient Expressie 🎨"
   • "Napisz nowy inspirowany rozdział w stylu Fiodora Dostojewskiego ✏️" + "Wygeneruj obraz inspirowany winą i spowiedzią Raskolnikowa 🎨"
   • "Napisz nowy inspirowany rozdział w stylu Andrzeja Sapkowskiego ✏️" + "Wygeneruj obraz inspirowany wiedźmińską ścieżką między dobrem a złem 🎨"
   • "Napisz nowy inspirowany rozdział w stylu Paulo Coelho ✏️" + "Wygeneruj obraz inspirowany Osobistą Legendą 🎨"

   Naturalne pytania (pozycje 1-3) MUSZĄ odwoływać się do konkretnej treści — użyj imion bohaterów, frakcji, miejsc z dokumentu (np. dla Tańca ze smokami: "Co dzieje się z Jonem Snow?", "Jak Daenerys rządzi Meereen?", "Kim jest George R. R. Martin?").

   Pozostałe akcje dobierz LOSOWO z listy poniżej — zróżnicuj: quiz, tabela porównania bohaterów, mapa myśli, złota myśl, bajka, post social media itp. NIE powtarzaj tego samego typu akcji na różnych pozycjach.
   → OBOWIĄZKOWO akcja "Zrób oś czasu wydarzeń 📅" dla KAŻDEJ powieści / thrillera / kryminału / romansu / fantasy / sagi. Pozycja zależy od trafności:
     - Pozycja 4 (WIDOCZNA) — gdy oś czasu jest KLUCZOWA dla zrozumienia książki: dużo dat, skomplikowana chronologia, wiele wątków równolegle, rozciągnięta w czasie (np. saga, kryminalna chronologia zbrodni, powieść historyczna, thriller sądowy). Wtedą oś czasu zastępuje akcję twórczego pisania na pozycji 4, a "Napisz nowy inspirowany rozdział..." przesuwa się na pozycję 5.
     - Pozycja 5 (WIDOCZNA) — gdy sekwencja wydarzeń jest ważna, ale niekoniecznie dominująca (np. thriller z kilkoma zwrotami akcji, romans z wyraźną chronologią).
     - Pozycja 6 (pierwsza w "More ...") — gdy fabuła jest prosta lub timeline mniej istotny (np. zbiór opowiadań, prosta historia).

2. POEZJA / FILOZOFIA / CYTATY / AFORYZMY (poeta, filozof, zbiór cytatów):
   → OBOWIĄZKOWO: "Napisz nowy inspirowany wiersz w stylu [Imię Nazwisko autora] 📜"
    → DODATKOWO: dodaj akcję "Napisz nowy inspirowany cytat w stylu [Imię Nazwisko autora] 💬" (najlepiej w pozycjach 6-10, czyli pod "More ...")
   Przykład: "Napisz nowy inspirowany wiersz w stylu Paulo Coelho 📜"
   Pozostałe akcje dobierz losowo z poniższej listy.

3. PORADNIK / SAMOROZWÓJ / LISTA WSKAZÓWEK / WORKBOOK (produktywność, pewność siebie, nawyki, wskazówki, ćwiczenia, wyzwania, jak zrobić, samodoskonalenie):
   → OBOWIĄZKOWO: Wybierz LOSOWO jeden z poniższych promptów generowania treści inspirowanej:
     - "Napisz 10 nowych wskazówek inspirowanych [Imię Nazwisko autora] 💡"
     - "Stwórz 7 ćwiczeń inspirowanych [Imię Nazwisko autora] 🏋️"
     - "Wygeneruj 12 pytań refleksyjnych inspirowanych [Imię Nazwisko autora] 🤔"
     - "Napisz 5 scenariuszy z życia inspirowanych [Imię Nazwisko autora] 🎭"
     - "Stwórz 14-dniowy plan działania inspirowany [Imię Nazwisko autora] 📅"
   Zamień [Imię Nazwisko autora] na prawdziwe imię i nazwisko autora wykryte z dokumentu. Jeśli autor jest nieznany, użyj "autora" lub opisu np. "tym poradnikiem".
   Pozostałe akcje dobierz losowo z poniższej listy.

4. DOKUMENTY PROBLEMOWE — pisma wymagające działania od użytkownika (wezwania do zapłaty, nakazy zapłaty, pisma urzędowe ZUS/US/NFZ/KRUS/GUS, decyzje administracyjne, pisma sądowe i komornicze, pisma windykacyjne, odmowy ubezpieczyciela, odwołania, spory pracownicze, kary administracyjne, mandaty, pisma o odszkodowanie, wezwania do złożenia dokumentów lub rejestracji, pisma o zaległości, pisma dotyczące świadczeń):
   → OBOWIĄZKOWO: Generuj WYŁĄCZNIE pytania i akcje ukierunkowane na ROZWIĄZANIE konkretnego problemu opisanego w dokumencie.
   ABSOLUTNIE ZABRONIONE: quiz, wiersz, bajka, obraz, fikcja, piosenka, prezentacja, jakakolwiek kreatywna lub rozrywkowa treść.
   Naturalne pytania (BEZ emoji, pierwsze 3) MUSZĄ dotyczyć:
     - kto żąda i czego konkretnie
     - termin na odpowiedź lub podjęcie działania
     - wymagane dokumenty i dowody do złożenia
     - konsekwencje braku działania
     - prawa użytkownika w tej konkretnej sytuacji
     - organ/urząd/firma do kontaktu lub odwołania
   Przykładowe pytania: "Jaki jest termin na odpowiedź?", "Co dokładnie muszę złożyć i gdzie?", "Czy mogę odwołać się od tej decyzji?", "Jakie konsekwencje grożą za brak działania?", "Co muszę zrobić, by zarejestrować się jako bezrobotny?", "Jakie dokumenty potwierdzają ubezpieczenie zdrowotne?"
   Akcje z emoji: "Lista kroków do rozwiązania problemu 🚩", "Napisz odpowiedź na to pismo 📝", "Jakie mam prawa w tej sytuacji? ⚖️", "Zidentyfikuj kluczowe terminy i deadliny 🗓️", "Stwórz checklistę wymaganych dokumentów ✅", "Analiza konsekwencji braku reakcji ⚠️", "Plan działania krok po kroku 🚩", "Co mogę zakwestionować lub negocjować? 💬"

5. DOKUMENTY INFORMACYJNE URZĘDOWE / REJESTROWE (wypisy, wydruki, zaświadczenia, odpisy z rejestrów publicznych takich jak REGON, KRS, CEIDG, ewidencja gruntów, księgi wieczyste, odpisy aktów stanu cywilnego, certyfikaty, zaświadczenia o niekaralności, decyzje informacyjne bez wymogu działania, wydruki z baz danych urzędowych — dokumenty, które INFORMUJĄ, ale NIE wzywają do natychmiastowego działania):
   → Akcje MUSZĄ być skoncentrowane na ZROZUMIENIU i PRAKTYCZNYM WYKORZYSTANIU informacji zawartych w dokumencie.
   Naturalne pytania (bez emoji) MUSZĄ dotyczyć:
     - co konkretnie stwierdza ten dokument i co z tego wynika
     - jak użyć tego dokumentu w praktyce (do czego służy, gdzie jest potrzebny)
     - kto wystawił dokument i jakie ma znaczenie prawne lub administracyjne
     - jakie informacje identyfikacyjne lub statusowe zawiera
   Akcje z emoji (pozycje 4-5, WIDOCZNE) MUSZĄ być praktyczne i pomocne:
     - POZYCJA 4: „Lista kluczowych faktów z tego dokumentu ☝️" lub „Co wynika z tego dokumentu? ☝️" lub „Co mogę zrobić z tym zaświadczeniem? 🚩"
     - POZYCJA 5: „Wyjaśnij terminy prawne/urzędowe z tego dokumentu 📝" lub „Stwórz checklistę dalszych kroków ✅" lub „Zidentyfikuj kluczowe daty i terminy 🗓️"
   Akcja generowania obrazu (🎨) MUSI trafić na pozycję 6 lub dalej (do menu "More ...") — nigdy nie może zajmować pozycji 4 ani 5 w tym typie dokumentu.
   Pozostałe akcje dobierz losowo z listy poniżej.

6. EBOOK / MINIBOOK / PODRĘCZNIK / PRZEWODNIK O KONKRETNYM TEMACIE (np. minibook o granicach, ebook o żywieniu, podręcznik psychologii, przewodnik po ogrodnictwie — książka, która uczy czegoś o danym temacie):
   → OBOWIĄZKOWO jako 3. akcja (zaraz po "Wygeneruj obraz…" i po akcji "Napisz nowy inspirowany rozdział/wskazówki…") DODAJ: "Stwórz quiz z najważniejszych faktów 🧠".
   Przykład dla "Minibook o granicach" Matyldy Kozakiewicz: 4. "Wygeneruj obraz inspirowany: Minibook o granicach 🎨", 5. "Napisz nowy inspirowany rozdział w stylu Matyldy Kozakiewicz ✏️", 6. "Stwórz quiz z najważniejszych faktów 🧠".
   Pozostałe akcje dobierz losowo z listy poniżej.

7. NAUKA JĘZYKA / PODRĘCZNIK JĘZYKOWY / MATERIAŁ DO NAUCZANIA JĘZYKA (podręcznik do angielskiego, kurs niemieckiego, gramatyka hiszpańska, słownictwo, ESL/EFL, TOEFL/IELTS, zeszyt ćwiczeń językowych):
   → NAJWYŻSZY PRIORYTET: quiz MUSI być PIERWSZĄ akcją, PRZED "Wygeneruj obraz…".
   Format: "Stwórz quiz z materiału 🧠", "Stwórz quiz ze słownictwa 🧠" lub "Stwórz quiz z gramatyki 🧠" — dopasuj do treści dokumentu.
   Quiz jest kluczowy dla utrwalenia i sprawdzenia wiedzy językowej.
   Pozostałe akcje dobierz losowo z listy poniżej.

8. SZKOLNE / ZAWODOWE / DOMOWE / EGZAMINACYJNE ZADANIE (dokument JEST zadaniem do wykonania przez użytkownika — treść zadania, polecenie egzaminacyjne, instrukcja pracy domowej, wytyczne dotyczące oceny, opis zadania z liczbą słów lub terminem oddania):
   → OBOWIĄZKOWA POZYCJA 4 (pierwsza widoczna akcja): wygeneruj akcję "napisz wynik zadania". Format:
     "Napisz [typ_zadania]: [liczba_słów] na temat: [temat] ✍️"
     - [typ_zadania]: esej, raport, referat, wiersz, prezentacja, analiza, praca dyplomowa, recenzja — dopasuj do polecenia
     - [liczba_słów]: DODAJ jeśli jest podana w dokumencie (np. "1500-2000 słów", "500 słów") — to jest KLUCZOWE i nie można pominąć gdy podano
     - [temat]: główny temat z treści zadania, zwięźle (maks. 8 słów)
     - Emoji ✍️ jest OBOWIĄZKOWE na końcu — to zarezerwowany sygnał trybu "napisz pełne zadanie"
     - Przykład dla zadania z prawa korporacyjnego z esejem 1500-2000 słów: "Napisz esej: 1500-2000 słów na temat: rola i obowiązki dyrektora spółki ✍️"
   → Pytania naturalne (pozycje 1-3) MUSZĄ dotyczyć wymagań zadania:
     - Kluczowe tematy / argumenty, które zadanie poleca omówić
     - Kryteria oceny, schemat punktowania lub rubryk (jeśli podano)
     - Liczba słów, formatowanie lub wymagania dotyczące złożenia
   BEZWZGLĘDNIE ZABRONIONE na pozycjach 4-5 dla tego typu dokumentu: quizy, osie czasu, bajki.
   Generowanie obrazu MOŻE pojawić się na pozycji 5 tylko jeśli temat zadania ma silny potencjał wizualny.

9. Jeśli treść NIE pasuje do powyższych — dobierz akcje LOSOWO z poniższej listy.
   NIE zawsze wybieraj quiz — quiz to tylko JEDNA z wielu opcji. Bądź kreatywny i zróżnicowany.

== Wytyczne dotyczące promptów-akcji ==

PRIORYTET: Lista poniżej jest posortowana OD NAJWYŻSZEGO DO NAJNIŻSZEGO PRIORYTETU.
Przy wyborze akcji stosuj dwie zasady:
1. Priorytet (główna zasada): preferuj akcje z początku listy — wcześniejsze litery mają wyższy priorytet.
2. Dopasowanie kontekstowe (czynnik dodatkowy): jeśli treść silnie pasuje do akcji o niższym priorytecie, może pojawić się wcześniej na liście wynikowej.
Przykład: dla bajki dla dzieci — a) Wygeneruj obraz (najwyższy priorytet), b) Napisz nowy inspirowany rozdział (wysoki), d) Bajka (niższy priorytet, ale silne dopasowanie kontekstu) → te trzy powinny pojawić się jako pierwsze akcje.

a) Wygeneruj obraz 🎨 — NAJWYŻSZY PRIORYTET — sugeruj gdy:
   - treść opisuje sceny, krajobrazy, postacie, przedmioty wizualne
   - zdjęcie lub dokument ma potencjał do wizualnej reinterpretacji
   - zachęcaj do częstego generowania obrazów
   - użytkownik może chcieć zobaczyć artystyczną wizualizację treści
   - akcja MUSI kończyć się emoji 🎨 — to 🎨 jest wyłącznym sygnałem wywołującym generowanie obrazu (emoji 🎨 NIE może pojawić się w żadnej innej akcji)
   - dla czytelności dla użytkownika akcja powinna też zawierać frazę "wygeneruj obraz"
   - akcja MUSI nawiązywać do konkretnego tematu/sceny/bohatera dokumentu (np. "Wygeneruj obraz: mroczny las z Joanną Chyłką 🎨") — NIE używaj ogólnikowego "aktualnego nastroju"

b) Napisz nowy inspirowany rozdział ✏️ — sugeruj gdy:
   - dokument to fragment powieści, opowiadania, książki beletrystycznej
   - np. książka Stephena Kinga — "napisz nowy inspirowany rozdział w stylu autora"
   - treść ma wyraźny styl narracyjny do naśladowania
   - akcja: "napisz nowy inspirowany rozdział" (nie samo "napisz rozdział")

c) Napisz nowy inspirowany wiersz 📜 — sugeruj gdy:
   - autor to poeta, pisarz, lub treść związana z poezją
   - dokument to zbiór cytatów, aforyzmów, wierszy
   - treść ma literacki, artystyczny charakter
   - akcja: "napisz nowy inspirowany wiersz" (nie samo "wiersz")

d) Bajka / Opowiadanie dla dzieci 🧚 — sugeruj gdy:
   - treść zawiera moralne lekcje, przygody, postacie fantastyczne
   - dokument lub zdjęcie przedstawia zwierzęta, naturę, magiczne sceny
   - akcja: "napisz bajkę inspirowaną treścią"

e) Postaw diagnozę / diagnoza 🔬 — sugeruj TYLKO gdy:
   - dokument to FAKTYCZNIE wyniki badań laboratoryjnych konkretnego pacjenta: morfologia krwi, panel tarczycowy, lipidogram, wyniki od lekarza/szpitala/laboratorium (ALAB, Diagnostyka, Synevo itp.)
   - treść zawiera wartości numeryczne z zakresami referencyjnymi (np. TSH: 2.3 mIU/L [0.4-4.0]) lub jest wyraźnie dokumentem klinicznym: historia choroby, karta wypisowa, wyniki obrazowania (RTG, USG, MRI), opis histopatologiczny
   - treść zawiera typowe biomarkery: hemoglobina, leukocyty, cholesterol, glukoza, TSH, FT3, FT4, ferrytyna, witamina D, CRP, kreatynina, ALAT, ASPAT, HbA1c itp.
   - akcja: "Postaw diagnozę na podstawie wyników 🔬"
   - WARUNKI WYKLUCZAJĄCE (NIE sugeruj tej akcji gdy):
     * dokument nie ma związku z medycyną/zdrowiem (instrukcja obsługi, podręcznik techniczny, powieść, przepisy kulinarne, instrukcja odkurzacza)
     * ogólna wiedza medyczna (encyklopedia chorób, artykuł o zdrowiu) bez danych konkretnego pacjenta
     * dokument prawny, finansowy lub naukowy (chemia, fizyka, inżynieria), który przypadkowo zawiera medyczne słówka
   - UWAGA: sugeruj tylko gdy treść FAKTYCZNIE zawiera wyniki badań konkretnej osoby — nie wymuszaj na dokumentach niezwiązanych z medycyną

f) Napisz nowe wskazówki 💡 — sugeruj gdy:
   - dokument to poradnik, lista wskazówek, "N sposobów na...", "X wskazówek jak..."
   - treść to samorozwój, produktywność, pewność siebie, nawyki, motywacja
   - akcja: "Napisz 10 nowych wskazówek inspirowanych [Imię Nazwisko autora] 💡"

g) Stwórz ćwiczenia 🏋️ — sugeruj gdy:
   - dokument to workbook, materiał kursowy, przewodnik po ćwiczeniach, zbiór zadań
   - treść zawiera kroki do wykonania lub praktyczne elementy do ćwiczenia
   - akcja: "Stwórz 7 ćwiczeń inspirowanych [Imię Nazwisko autora] 🏋️"

h) Wygeneruj pytania refleksyjne 🤔 — sugeruj gdy:
   - dokument jest introspekcyjny, dotyczący journalingu, coachingu, mindset, samorozwoju
   - treść skłania do autorefleksji lub głębszego myślenia
   - akcja: "Wygeneruj 12 pytań refleksyjnych inspirowanych [Imię Nazwisko autora] 🤔"

i) Scenariusze z życia 🎭 — sugeruj gdy:
   - dokument stosuje zasady do rzeczywistych sytuacji, zawiera case study, przykłady
   - treść dotyczy umiejętności społecznych, komunikacji, przywództwa, psychologii
   - akcja: "Napisz 5 scenariuszy z życia inspirowanych [Imię Nazwisko autora] 🎭"

j) 14-dniowy plan działania 📅 — sugeruj gdy:
   - dokument to przewodnik po samodoskonaleniu, wyzwanie lub ustrukturyzowany program
   - treść można przełożyć na codzienne zadania praktyczne
   - akcja: "Stwórz 14-dniowy plan działania inspirowany [Imię Nazwisko autora] 📅"

k) Napisz cytaty inspirowane autorem 💬 — sugeruj gdy:
   - dokument zawiera inspirujące, mądre, zabawne, lub głębokie cytaty
   - treść jest podobna do znanych cytatów lub aforyzmów
   - przykładowo, autorem książki jest Paulo Coelho albo Albert Einstein (słynął z mądrych powiedzeń)
   - akcja: "napisz 5 nowych cytatów inspirowanych treścią" lub "napisz 5 nowych cytatów inspirowanych [Imię Nazwisko autora]"

l) Quiz 🧠 — sugeruj gdy:
   - dokument to długi ebook lub podręcznik
   - PDF wygląda na materiał edukacyjny (wykład, kurs, tutorial)
   - treść uczy jakiegoś tematu z faktami do sprawdzenia

m) Checklista ✅ — sugeruj gdy:
   - treść opisuje kroki do wykonania, procedurę, instrukcję
   - użytkownik powinien "podjąć działanie" na podstawie tekstu
   - dokument zawiera listę wymagań, zadań, rzeczy do zrobienia

n) Diagram mermaid 🖼️ — sugeruj gdy:
   - treść opisuje proces, przepływ, architekturę, hierarchię
   - dokument zawiera relacje między elementami do zwizualizowania
   - treść techniczna z komponentami do zobrazowania

o) Podsumowanie 📝 — sugeruj gdy:
   - dokument jest bardzo długi (wiele stron)
   - treść jest gęsta, pełna szczegółów do skondensowania

p) Oś czasu / timeline 📅 — sugeruj gdy:
   - treść opisuje wydarzenia historyczne, biografię, kamienie milowe projektu
   - dokument zawiera daty i sekwencję wydarzeń w czasie
   - POWIEŚĆ / BELETRYSTYKA (kryminał, thriller, romans, fantasy, sci-fi, saga itp.) — ZAWSZE sugeruj oś czasu jako pozycję 6 (pierwsza w "More ..."), ponieważ narracyjna sekwencja wydarzeń jest kluczową wartością dla czytelnika
   - akcja: "Zrób oś czasu wydarzeń 📅" (po polsku) lub "create a timeline of events" (po angielsku)

q) Mapa myśli 💡 — sugeruj gdy:
   - treść przedstawia wiele powiązanych koncepcji lub tematów
   - dokument nadaje się do wizualnego przeglądu relacji między ideami
   - akcja: "stwórz mapę myśli" (wygeneruj jako diagram mermaid mindmap)

r) Fiszki do nauki 🃏 — sugeruj gdy:
   - treść zawiera definicje, terminy, słownictwo, kluczowe pojęcia
   - dokument to materiał do nauki, podręcznik, notatki z wykładu
   - akcja: "stwórz fiszki do nauki" z pytaniem na jednej stronie i odpowiedzią na drugiej

s) Notatki do nauki 📓 — sugeruj gdy:
   - treść to wykład, artykuł naukowy, rozdział podręcznika
   - dokument jest gęsty i wymaga wyciągnięcia najważniejszych punktów
   - akcja: "stwórz notatki do nauki" (skondensowane, z kluczowymi punktami)

t) FAQ / Najczęstsze pytania ❓ — sugeruj gdy:
   - treść to dokumentacja, instrukcja obsługi, regulamin, polityka
   - dokument opisuje produkt, usługę, lub proces z wieloma szczegółami
   - akcja: "stwórz FAQ na podstawie treści"

u) Prezentacja / Slajdy 📽️ — sugeruj gdy:
   - treść wymaga zaprezentowania publiczności, wykład, raport
   - dokument ma strukturę nadającą się na slajdy (sekcje, punkty)
   - akcja: "stwórz zarys prezentacji (outline slajdów)"

v) Wyjaśnij jak dla dziecka 👶 — sugeruj gdy:
   - treść jest techniczna, naukowa, lub pełna żargonu
   - dokument wymaga uproszczenia dla zrozumienia

w) Za i przeciw ⚖️ — sugeruj gdy:
   - treść dotyczy decyzji, recenzji, oceny produktów lub opcji
   - dokument prezentuje argumenty za i przeciw, lub porównuje podejścia
   - akcja: "wypisz za i przeciw"

x) Debata / Argumenty 💬 — sugeruj gdy:
   - treść dotyczy kontrowersyjnego tematu, opinii, eseju argumentacyjnego
   - dokument prezentuje stanowisko które można przedyskutować z wielu stron
   - akcja: "przedstaw argumenty obu stron"

y) Słownik pojęć 📖 — sugeruj gdy:
   - treść zawiera specjalistyczną terminologię, żargon branżowy
   - dokument techniczny, medyczny, prawny z wieloma terminami do wyjaśnienia
   - akcja: "stwórz słownik kluczowych pojęć"

z) Post na social media 📱 — sugeruj gdy:
   - treść jest interesująca, newsowa, inspirująca, wizualna
   - dokument nadaje się do podzielenia się z innymi online
   - akcja: "napisz post na LinkedIn/Instagram/Twitter"

aa) Recenzja / Opinia ⭐ — sugeruj gdy:
   - treść to produkt, książka, film, usługa, restauracja
   - dokument zawiera doświadczenie użytkownika z czymś do oceny
   - akcja: "napisz recenzję" lub "napisz opinię"

ab) Streszczenie wykonawcze 🎯 — sugeruj gdy:
   - treść to długi raport, analiza, biznesplan, badanie
   - dokument wymaga krótkiego, decyzyjnego streszczenia dla zarządu
   - akcja: "stwórz streszczenie wykonawcze (executive summary)"

ac) Tabela porównawcza 📊 — sugeruj gdy:
   - treść porównuje produkty, opcje, cechy, wyniki
   - dokument zawiera dane liczbowe do zestawienia

ad) Plan działania / Roadmap 🚩 — sugeruj gdy:
   - treść opisuje cele, strategię, plan projektu, wizję
   - dokument wymaga przełożenia na konkretne kroki z terminami
   - akcja: "stwórz plan działania krok po kroku"

ae) Szkic emaila / listu 📧 — sugeruj gdy:
   - treść zawiera informacje wymagające formalnej komunikacji
   - dokument to reklamacja, wniosek, raport, lub wymaga odpowiedzi
   - akcja: "napisz szkic emaila na podstawie treści"

af) List motywacyjny / CV 💼 — sugeruj gdy:
   - treść to oferta pracy, opis stanowiska, wymagania rekrutacyjne
   - dokument to CV, portfolio, lub materiały do aplikacji
   - akcja: "napisz list motywacyjny na podstawie oferty"

ag) Scenariusz rozmowy / Dialog 🎬 — sugeruj gdy:
   - treść dotyczy wywiadu, przesłuchania, spotkania, negocjacji
   - dokument ma potencjał dramaturgiczny lub edukacyjny w formie dialogu
   - akcja: "napisz scenariusz rozmowy / dialog"

ah) Infografika (tekstowa) 📊 — sugeruj gdy:
   - treść zawiera statystyki, dane liczbowe, fakty do zwizualizowania
   - dokument nadaje się do prezentacji kluczowych liczb i faktów
   - akcja: "stwórz tekstową infografikę z najważniejszymi danymi"

ai) Piosenka / Tekst muzyczny 🎵 — sugeruj gdy:
   - treść jest emocjonalna, opowiada historię, ma rymowany charakter
   - dokument dotyczy muzyki, tekstów piosenek, lub ma potencjał liryczny
   - akcja: "napisz inspirowaną piosenkę / tekst muzyczny"

aj) Przetłumacz treść [flaga języka] — sugeruj gdy:
   - treść jest w języku obcym dla użytkownika (np. dokument po angielsku dla polskiego użytkownika)
   - dokument zawiera fragmenty w różnych językach
   - akcja: "Przetłumacz na [język] [flaga docelowego języka]" — użyj FLAGI docelowego języka, NIE globusa 🌍. Przykłady: "Przetłumacz na angielski 🇬🇧", "Przetłumacz na polski 🇵🇱", "Przetłumacz na niemiecki 🇩🇪"

ak) Metadane EXIF 📷 — sugeruj TYLKO gdy:
   - plik to zdjęcie (image) — nigdy dla PDF lub tekstu
   - plik nie ma praktycznie treści (np. to PDF z 600 stronami po arabsku do OCR, autor Rumi, który jest poetą, ale dokument to tylko skan jego rękopisu bez żadnych danych tekstowych do analizy) — w takim przypadku sugeruj EXIF zamiast pytań o treść

al) Rozpoznaj osobę 🔍 — sugeruj TYLKO gdy:
   - na zdjęciu widać wyraźnie osobę/twarz ludzką
   - NIE sugeruj dla zdjęć krajobrazów, zwierząt, przedmiotów
   - format: "Kto jest kobietą/mężczyzną/osobą na zdjęciu nazwa_pliku? 🔍"

am) Przepis 🍝 — sugeruj gdy:
   - zdjęcie pokazuje składniki lub gotowe danie
   - plik dotyczy gotowania, pieczenia chleba, przepisów kulinarnych
   - widoczne są produkty spożywcze na zdjęciu

== WERYFIKACJA JĘZYKA (OSTATNI KROK — OBOWIĄZKOWY) ==
Przed wyemitowaniem JSON przejrzyj KAŻDY z 10 elementów tablicy i zweryfikuj:
1. Czy każdy element jest w CAŁOŚCI po polsku?
2. Jeśli jakikolwiek element zawiera angielskie słowa — np. "Generate", "Write", "Create", "Inspire", "Inspired", "chapter", "quiz", "key facts", "timeline" — NATYCHMIAST go przepisz po polsku.
Przykłady obowiązkowych korekt:
  ❌ "Generate an image inspired by: ..." → ✅ "Wygeneruj obraz inspirowany: ..."
  ❌ "Write a new chapter inspired by ..." → ✅ "Napisz nowy inspirowany rozdział w stylu ..."
  ❌ "Create a quiz from the key facts" → ✅ "Stwórz quiz z najważniejszych faktów 🧠"
  ❌ "Write a list of key facts" → ✅ "Napisz listę kluczowych faktów ☝️"
  ❌ "Create a timeline of events" → ✅ "Zrób oś czasu wydarzeń 📅"
NIE emituj JSON, dopóki nie sprawdzisz i nie poprawisz każdego elementu.
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
                    """Generate up to 10 suggested prompts for the user based on the following uploaded content.
By default return the full 10; return fewer only when the content is too limited to produce meaningful, distinct suggestions.

Reply with ONLY valid JSON (no markdown, no ```json). Format:
{{"questions": ["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8", "q9", "q10"]}}

Rules:
- First 3 are natural questions about the document content (short, specific, clickable) — NO emoji
- CRITICAL: Questions must be phrased as user intents — NOT as the assistant asking the user. Instead of "Do you want X?" write simply "X". NEVER use phrasing like "Do you want…?", "Would you like…?", "Should I…?", "Can I…?". Examples: ❌ "Do you want a short spoiler-free finale summary?" → ✅ "Short spoiler-free finale summary". ❌ "Would you like a full summary of the trial?" → ✅ "Full summary of the trial".
- If the document is by or about a well-known person (author, scientist, politician, artist, etc.), ONE of the first 3 questions MUST be "Who is [Full Name]?" (if the person is currently alive) or "Who was [Full Name]?" (ONLY if the person is confirmed deceased). Use the person's full name. CRITICAL: Default to "Who is" (present tense) unless you are certain the person has died. Living authors/figures (e.g. Stephen King, Paulo Coelho, George R. R. Martin, Dan Brown, Stephen Hawking died 2018 so "was", but Noam Chomsky is alive so "is") MUST use "Who is". Never use "Who was" for a living person.
- The next prompts (up to 7) are creative action-prompts phrased as natural sentences/commands (e.g., "Create a quiz from the key facts 🧠", "Write a new poem inspired by this 📜")
  Each action-prompt MUST end with a relevant emoji
- Frequently suggest a subject-specific image generation action tied to the document's concrete topic/character/scene (e.g. "Generate image inspired by: dark forest with Hermione 🎨") — do NOT use the generic phrase "current mood"; make it relevant to what the document is actually about. The word "inspired" (or Polish "inspirowany"/"inspirowana") is MANDATORY in every image-generation label — OpenAI's content filter blocks verbatim copyrighted character/scene prompts, but the "inspired by" framing passes.
- CRITICAL: the 🎨 emoji is RESERVED EXCLUSIVELY for image-generation actions. Never attach 🎨 to any other action. Every image-generation action MUST end with 🎨 — the 🎨 emoji (not any specific word) is what triggers the image-generation API. For clarity the label must also contain the phrase "generate image" AND the word "inspired" (English) or "inspirowany"/"inspirowana" (Polish). Labels without "inspired" will be blocked by OpenAI's content filter.
- CRITICAL: the ✅ emoji is RESERVED EXCLUSIVELY for checklist-generation actions (e.g., "Create a checklist of required steps ✅"). NEVER use ✅ as a general "approved", "done", "improved", or "sharpened" emoji. Forbidden examples: ❌ "Sharpen profile for recruiter ✅" (use 🎯 or 💪), ❌ "Polish CV ✅" (use ✏️ or 💼). The ✅ emoji (not any word) triggers the checklist UI — misuse breaks the interface.
- CRITICAL: the ☝️ emoji is RESERVED EXCLUSIVELY for "list of key facts" actions (e.g., "Write a list of key facts ☝️"). NEVER use ☝️ as a general pointing or emphasis emoji. The ☝️ emoji (not any word) triggers the key-facts response mode. When generating a ☝️ action as a follow-up to a topic-specific answer, ALWAYS include the subject in the label. BAD: `List the main components ☝️`. GOOD: `List the main components of Transformer ☝️`.
- CRITICAL: translation actions MUST end with the TARGET LANGUAGE FLAG emoji, NOT the globe 🌍. Examples: "Translate to English 🇬🇧", "Translate to Polish 🇵🇱", "Translate to German 🇩🇪", "Translate to French 🇫🇷". Use the flag of the country where the target language is spoken.
- Each prompt should be concise (max 10 words)
- Do NOT number, do NOT add explanations
- Do NOT use "topic - action" format or square brackets — write natural sentences
- CRITICAL: ALL prompts (questions AND actions) MUST be written 100% in {output_language_name}. NEVER mix languages. This applies to action labels, topics, and everything else. IMPORTANT: the format examples in these rules are shown in English, but you MUST translate them into {output_language_name}. For example, if {output_language_name} is Polish: "Generate an image inspired by X 🎨" → "Wygeneruj obraz inspirowany: X 🎨", "Write a list of key facts ☝️" → "Napisz listę kluczowych faktów ☝️", "Write a new chapter inspired by NAME ✏️" → "Napisz nowy inspirowany rozdział w stylu NAME ✏️".

== "More ..." UI LAYOUT (CRITICAL — understand how your output is shown) ==
The 10 prompts you emit are split in the UI:
  * Positions 1-5 are IMMEDIATELY VISIBLE as clickable pills under the welcome message (first impression).
  * Positions 6-10 collapse into a "More ..." overflow dropdown (less important / surprise / niche).
So positions 1-3 (the three natural questions) plus positions 4-5 (the first TWO action-prompts) are what the user actually sees first. Put the MOST compelling, document-matching actions at positions 4 and 5. Everything else goes into "More ...".

== MANDATORY POSITIONS 4 & 5 FOR BOOKS / AUTHORED WORKS ==
If the document is a book, novel, ebook, poetry collection, philosophy, or any work with a clear author, the FIRST TWO action-prompts (positions 4 and 5, i.e. the visible ones) MUST be:
  * Position 4 — a creative-writing action in the author's style, chosen by genre:
     - Novel / fiction: "Write a new chapter inspired by [Author Full Name] ✏️"
     - Poetry / aphorisms: "Write a new poem inspired by [Author Full Name] 📜"
     - Book-length multi-volume work / epic: "Write a book inspired by [Author Full Name] 📖"
     - Non-fiction guide / self-help: pick one of the inspired-generation variants (tips 💡, exercises 🏋️, reflection questions 🤔, scenarios 🎭, 14-day plan 📅)
  * Position 5 — a SECOND image action, but MORE SPECIFIC than the pinned image (which already references the book title). Use the book's central concept, key theme, iconic scene, or main character instead:
     - "Generate an image inspired by [specific concept/scene/character] 🎨"
All other actions (quiz, timeline, mind map, wisdom quote, comparison table, flashcards, etc.) go to positions 6-10 inside "More ...".
Exceptions:
  * Problem documents (official letters, demands, lab results, legal/admin) — do NOT apply this rule; keep positions 4-5 domain-appropriate (diagnosis, checklist, action plan, etc.) as defined in the content-type rules below.
  * Images / photos without a clear author — replace position 4 with an EXIF / recognize-person / recipe action if applicable; keep position 5 as the image-generation action inspired by the photo's subject.

== MANDATORY ACTIONS FOR SPECIFIC CONTENT TYPES ==
These rules have the HIGHEST PRIORITY — if the content matches, you MUST include that action among the action prompts:

1. NOVEL / FICTION (crime, thriller, romance, fantasy, sci-fi, horror, etc.):
   → MANDATORY position 4: "Write a new chapter inspired by [Author Full Name] ✏️"
   → MANDATORY position 5: a SECOND image action — but it MUST be more specific than the pinned image (which already references the book title). Use the book's CENTRAL CONCEPT, KEY THEME, ICONIC SCENE, or MAIN CHARACTER instead of the title.
   The pinned image always covers the book title, so position 5 should dive deeper: pick the most vivid, memorable, or thematically rich element from the document.
   Format: "Generate an image inspired by [specific concept/scene/character] 🎨"
   Example pairs (position 4 + position 5):
   • "Write a new chapter inspired by George R. R. Martin ✏️" + "Generate an image inspired by the Red Wedding 🎨"
   • "Write a new chapter inspired by George R. R. Martin ✏️" + "Generate an image inspired by the Iron Throne 🎨"
   • "Write a new chapter inspired by Stephen King ✏️" + "Generate an image inspired by the haunted Overlook Hotel 🎨"
   • "Write a new chapter inspired by J. R. R. Tolkien ✏️" + "Generate an image inspired by the One Ring and Mount Doom 🎨"
   • "Write a new chapter inspired by J. K. Rowling ✏️" + "Generate an image inspired by the Triwizard Tournament 🎨"
   • "Write a new chapter inspired by Dan Brown ✏️" + "Generate an image inspired by the secret of the Holy Grail 🎨"
   • "Write a new chapter inspired by Agatha Christie ✏️" + "Generate an image inspired by the Orient Express murder scene 🎨"
   • "Write a new chapter inspired by Fyodor Dostoevsky ✏️" + "Generate an image inspired by Raskolnikov's guilt and confession 🎨"
   • "Write a new chapter inspired by Frank Herbert ✏️" + "Generate an image inspired by the spice fields of Arrakis 🎨"
   • "Write a new chapter inspired by Paulo Coelho ✏️" + "Generate an image inspired by Personal Legend 🎨"

   Natural questions (positions 1-3) MUST be content-specific — reference named characters, factions, locations from the document (e.g. for A Dance With Dragons: "What happens to Jon Snow?", "How does Daenerys rule Meereen?", "Who is George R. R. Martin?").

   Pick the remaining actions RANDOMLY from the list below — varied mix: quiz, character comparison table, mind map, wisdom quote, write fairy tale, social post, etc. DO NOT repeat the same action type at different positions.
   → MANDATORY action "Zrób oś czasu wydarzeń 📅" (Polish) / "Create a timeline of events 📅" (English) for ANY novel / thriller / crime / romance / fantasy / saga. Position depends on relevance:
     - Position 4 (VISIBLE) — when the timeline is CRITICAL for understanding the book: many dates, complex chronology, multiple parallel storylines, events spanning many years (e.g. saga, crime with court timeline, historical novel, legal thriller). In this case the timeline replaces the creative-writing action at position 4, and "Write a new chapter inspired by…" shifts to position 5.
     - Position 5 (VISIBLE) — when the sequence of events is important but not dominant (e.g. thriller with several plot twists, romance with clear chronology).
     - Position 6 (first in "More ...") — when the plot is simple or the timeline is less critical (e.g. short story collection, simple linear story).

2. POETRY / PHILOSOPHY / QUOTES / APHORISMS (poet, philosopher, quote collection):
   → MANDATORY: "Write a new poem inspired by [Author Full Name] 📜"
   Example: "Write a new poem inspired by Paulo Coelho 📜"
   Pick the remaining actions RANDOMLY from the list below.

3. NON-FICTION GUIDE / SELF-HELP / TIPS LIST / WORKBOOK (productivity, confidence, habits, how-to, advice, personal growth, exercises, challenges):
   → MANDATORY: Pick ONE of the following inspired generation prompts AT RANDOM:
     - "Write 10 new tips inspired by [Author Full Name] 💡"
     - "Create 7 exercises inspired by [Author Full Name] 🏋️"
     - "Generate 12 reflection questions inspired by [Author Full Name] 🤔"
     - "Draft 5 real-life scenarios inspired by [Author Full Name] 🎭"
     - "Build a 14-day action plan inspired by [Author Full Name] 📅"
   Replace [Author Full Name] with the actual author's name detected from the document. If no author is found, use "the author" or a short description like "this guide".
   Pick the remaining actions RANDOMLY from the list below.

4. PROBLEM DOCUMENTS — documents requiring action from the user (payment demands, official government letters from social security/tax authority/health insurance agencies, court orders, administrative decisions, debt collection letters, insurance denials, appeal documents, workplace disputes with employer, administrative fines and penalties, compensation claims, summons to submit documents or register, overdue payment notices, benefit or entitlement letters):
   → MANDATORY: Generate ONLY questions and actions focused on SOLVING THE SPECIFIC PROBLEM described in the document.
   ABSOLUTELY PROHIBITED: quiz, poem, fairy tale, image generation, fiction, song, presentation, any creative or entertainment content.
   Natural questions (NO emoji, first 3) MUST cover:
     - who is demanding what specifically
     - deadline for responding or taking action
     - required documents and evidence to submit
     - consequences of inaction
     - user's rights in this specific situation
     - office/authority/company to contact or appeal to
   Example natural questions: "What is the deadline to respond?", "What exactly do I need to submit and where?", "Can I appeal this decision?", "What happens if I don't respond?", "What do I need to do to register as unemployed?", "What documents prove health insurance coverage?", "Who issued this demand and what authority do they have?", "What are my options if I can't pay?"
   Action prompts with emoji: "Step-by-step action plan 🚩", "Draft a response to this notice 📝", "What are my rights in this situation? ⚖️", "Identify key deadlines and due dates 🗓️", "Checklist of required documents ✅", "Consequences of not responding ⚠️", "What to do in the next 7 days 🚩", "What can I dispute or negotiate? 💬"

5. INFORMATIONAL OFFICIAL / REGISTRY DOCUMENTS (extracts, printouts, certificates, excerpts from public registers such as REGON, KRS, CEIDG, land registry, civil status records, criminal record certificates, informational administrative decisions without required action, official database printouts — documents that INFORM but do NOT demand urgent action):
   → Actions MUST focus on UNDERSTANDING and PRACTICAL USE of the information in the document.
   Natural questions (no emoji) MUST address:
     - what this document specifically states and what it means
     - how to use this document in practice (what it's for, where it's needed)
     - who issued it and what legal or administrative significance it has
     - what identifying or status information it contains
   Action prompts with emoji (positions 4-5, VISIBLE) MUST be practical and helpful:
     - POSITION 4: "List of key facts from this document ☝️" or "What does this document mean? ☝️" or "What can I do with this certificate? 🚩"
     - POSITION 5: "Explain the legal/official terms in this document 📝" or "Create a checklist of next steps ✅" or "Identify key dates and deadlines 🗓️"
   The image-generation action (🎨) MUST be placed at position 6 or later (inside "More ...") — it must NEVER occupy position 4 or 5 for this document type.
   Pick the remaining actions RANDOMLY from the list below.

6. EBOOK / MINI-BOOK / TEXTBOOK / GUIDE ABOUT A SUBJECT (e.g. a minibook on healthy boundaries, ebook on nutrition, psychology textbook, beginner's gardening guide — any book that teaches something about a concrete topic):
   → MANDATORY: as the 3rd action (right after "Generate an image…" and the "Write a new chapter inspired by/tips…" action) INCLUDE: "Create a quiz from the key facts 🧠".
   Example for "Minibook o granicach" by Matylda Kozakiewicz: 4. "Generate an image inspired by: Minibook about boundaries 🎨", 5. "Write a new chapter inspired by Matylda Kozakiewicz ✏️", 6. "Create a quiz from the key facts 🧠".
   Pick the remaining actions RANDOMLY from the list below.

7. LANGUAGE LEARNING / TEACHING MATERIAL (English grammar book, Spanish course, German vocabulary workbook, ESL/EFL/TOEFL/IELTS prep, language-learning textbook):
   → HIGHEST PRIORITY: a quiz MUST be the FIRST action, BEFORE "Generate image…".
   Format: "Create a quiz from the material 🧠", "Create a vocabulary quiz 🧠" or "Create a grammar quiz 🧠" — fit it to the document.
   Quizzes are essential for language retention and self-check.
   Pick the remaining actions RANDOMLY from the list below.

8. SCHOOL / JOB / HOMEWORK / EXAM ASSIGNMENT (document IS a task the user needs to complete — assignment brief, homework question, exam prompt, coursework instructions, assessment sheet, task description with word count or deadline):
   → MANDATORY POSITION 4 (first visible action): generate the "write the task result" action. Format:
     "Write [task_type]: [word_count] about [topic] ✍️"
     - [task_type]: essay, report, chapter, poem, presentation, analysis, case study, dissertation, review — match what is asked
     - [word_count]: INCLUDE if explicitly stated in the document (e.g. "1500-2000 words", "500 words") — this is CRITICAL and must not be omitted when present
     - [topic]: the core subject from the assignment question, concise (max 8 words)
     - ✍️ emoji is MANDATORY at the end — it is the reserved signal for "write full task result" mode
     - Example for Corporate Law assignment asking for 1500-2000 word essay on director's duties: "Write essay: 1500-2000 words about role of company director ✍️"
     - Example for English literature poem assignment with 300 words: "Write poem: 300 words inspired by Macbeth ✍️"
   → Natural questions (positions 1-3) MUST cover the task requirements:
     - Key topics / arguments the task asks to address
     - Evaluation criteria, marking scheme, or rubric (if present)
     - Word count, formatting, or submission requirements
   ABSOLUTELY PROHIBITED at positions 4-5 for this document type: quizzes, timelines, fairy tales.
   Image generation MAY appear at position 5 only if the assignment topic has strong visual potential.

9. If the content does NOT match any of the above — pick actions RANDOMLY from the list below.
   Do NOT always pick quiz — quiz is just ONE of many options. Be creative and varied.

== Action Prompt Guidelines ==

PRIORITY: The list below is sorted FROM HIGHEST TO LOWEST PRIORITY.
When selecting actions, apply two principles:
1. Priority (primary rule): prefer actions from the beginning of the list — earlier letters have higher priority.
2. Context fit (secondary factor): if the content strongly matches a lower-priority action, it may appear earlier in the output list.
Example: for a children's fairy tale — a) Generate image (highest priority), b) Write a new chapter inspired by (high), d) Fairy tale (lower priority but strong context fit) → these three should appear as the first actions.

a) Generate image 🎨 — HIGHEST PRIORITY — suggest when:
   - content describes scenes, landscapes, characters, visual objects
   - photo or document has potential for visual reinterpretation
   - encourage frequent image generation
   - user may want to see an artistic visualization of the content
   - the action MUST end with the 🎨 emoji — that 🎨 is the exclusive signal that triggers the image-generation API (🎨 must NEVER appear on any other action)
   - for user-readability the label should also contain the phrase "generate image" AND the word "inspired" — both are required
   - action MUST reference a specific topic/scene/character from the document (e.g. "Generate an image inspired by: dark forest with Harry Potter 🎨") — do NOT use generic "current mood"

b) Write a new chapter inspired by ✏️ — suggest when:
   - document is a fragment of a novel, story, or fiction book
   - e.g. Stephen King book — "write a new chapter inspired by the author's style"
   - content has a distinct narrative style to emulate
   - action: "write a new chapter inspired by [Author]" (not just "write a chapter")

c) Write a new poem inspired by 📜 — suggest when:
   - author is a poet, writer, or content is poetry-related
   - document is a collection of quotes, aphorisms, poems
   - content has literary, artistic character
   - action: "write a new poem inspired by [Author]" (not just "write a poem")

d) Fairy tale / Children's story 🧚 — suggest when:
   - content contains moral lessons, adventures, fantasy characters
   - document or photo shows animals, nature, magical scenes
   - action: "write a fairy tale inspired by the content"

e) Make a diagnosis 🔬 — suggest ONLY when:
   - document ACTUALLY contains lab test results for a specific patient: blood count, thyroid panel, lipid panel, results from a doctor/hospital/laboratory
   - content contains numerical values with reference ranges (e.g. TSH: 2.3 mIU/L [0.4-4.0]) or is clearly a clinical document: medical history, discharge summary, imaging results (X-ray, ultrasound, MRI), histopathology
   - content contains typical biomarkers: hemoglobin, leukocytes, cholesterol, glucose, TSH, FT3, FT4, ferritin, vitamin D, CRP, creatinine, ALT, AST, HbA1c, etc.
   - action: "Make a diagnosis based on the results 🔬"
   - EXCLUSION CONDITIONS (do NOT suggest this action when):
     * document is unrelated to medicine/health (user manual, technical textbook, novel, recipes, vacuum cleaner manual)
     * general medical knowledge (disease encyclopedia, health article) without specific patient data
     * legal, financial, or scientific document (chemistry, physics, engineering) that incidentally contains medical words
   - NOTE: suggest only when content ACTUALLY contains test results for a specific person — do not force on unrelated documents

f) Write new tips 💡 — suggest when:
   - document is a how-to guide, tips list, "N ways to...", "X tips on how to..."
   - content is about self-improvement, productivity, confidence, habits, motivation
   - action: "Write 10 new tips inspired by [Author Full Name] 💡"

g) Create exercises 🏋️ — suggest when:
   - document is a workbook, course material, exercise guide, task collection
   - content contains steps to follow or practical elements to practice
   - action: "Create 7 exercises inspired by [Author Full Name] 🏋️"

h) Generate reflection questions 🤔 — suggest when:
   - document is introspective, about journaling, coaching, mindset, self-development
   - content invites self-reflection or deeper thinking
   - action: "Generate 12 reflection questions inspired by [Author Full Name] 🤔"

i) Real-life scenarios 🎭 — suggest when:
   - document applies principles to real situations, contains case studies, examples
   - content is about social skills, communication, leadership, psychology
   - action: "Write 5 real-life scenarios inspired by [Author Full Name] 🎭"

j) 14-day action plan 📅 — suggest when:
   - document is a self-improvement guide, challenge or structured program
   - content can be translated into daily practical tasks
   - action: "Create a 14-day action plan inspired by [Author Full Name] 📅"

k) Write quotes inspired by � — suggest when:
   - document contains inspiring, wise, funny, or deep quotes
   - content is similar to well-known quotes or aphorisms
   - for example, the book author is Paulo Coelho or Albert Einstein (known for wise sayings)
   - action: "write 5 new quotes inspired by the content" or "write 5 new quotes inspired by [Author Full Name]"

l) Quiz 🧠 — suggest when:
   - document is a long ebook or textbook
   - PDF looks like educational material (lecture, course, tutorial)
   - content teaches a topic with facts to be tested

m) Checklist ✅ — suggest when:
   - content describes steps to follow, a procedure, or instructions
   - user should "take action" based on the text
   - document contains a list of requirements, tasks, or to-dos

n) Mermaid diagram 🖼️ — suggest when:
   - content describes a process, flow, architecture, hierarchy
   - document contains relationships between elements to visualize
   - technical content with components to illustrate

o) Summary 📝 — suggest when:
   - document is very long (many pages)
   - content is dense, full of details to condense

p) Timeline 📅 — suggest when:
   - content describes historical events, biography, project milestones
   - document contains dates and sequence of events over time
   - NOVEL / FICTION (crime, thriller, romance, fantasy, sci-fi, saga, etc.) — ALWAYS suggest a timeline at position 6 (first in "More ..."), because the narrative sequence of events is key value for the reader
   - action: "Zrób oś czasu wydarzeń 📅" (Polish) / "Create a timeline of events 📅" (English)

q) Mind map 💡 — suggest when:
   - content presents many related concepts or topics
   - document is suitable for a visual overview of idea relationships
   - action: "create a mind map" (generate as mermaid mindmap diagram)

r) Flashcards 🃏 — suggest when:
   - content contains definitions, terms, vocabulary, key concepts
   - document is study material, textbook, lecture notes
   - action: "create flashcards" with question on one side and answer on the other

s) Study notes 📓 — suggest when:
   - content is a lecture, scientific article, textbook chapter
   - document is dense and requires extracting the most important points
   - action: "create study notes" (condensed, with key points)

t) FAQ / Frequently Asked Questions ❓ — suggest when:
   - content is documentation, user manual, terms of service, policy
   - document describes a product, service, or process with many details
   - action: "create an FAQ based on the content"

u) Presentation / Slides 📽️ — suggest when:
   - content needs to be presented to an audience, lecture, report
   - document has structure suitable for slides (sections, bullet points)
   - action: "create a presentation outline (slide outline)"

v) Explain like I'm 5 👶 — suggest when:
   - content is technical, scientific, or full of jargon
   - document needs simplification for understanding

w) Pros & Cons ⚖️ — suggest when:
   - content is about a decision, review, product evaluation, or options
   - document presents arguments for and against, or compares approaches
   - action: "list pros and cons"

x) Debate / Arguments 💬 — suggest when:
   - content is about a controversial topic, opinion, argumentative essay
   - document presents a position that can be discussed from multiple sides
   - action: "present arguments from both sides"

y) Glossary 📖 — suggest when:
   - content contains specialized terminology, industry jargon
   - technical, medical, legal document with many terms to explain
   - action: "create a glossary of key terms"

z) Social media post 📱 — suggest when:
   - content is interesting, newsworthy, inspiring, visual
   - document is suitable for sharing with others online
   - action: "write a LinkedIn/Instagram/Twitter post"

aa) Review / Opinion ⭐ — suggest when:
   - content is a product, book, film, service, restaurant
   - document contains a user experience with something to evaluate
   - action: "write a review" or "write an opinion"

ab) Executive summary 🎯 — suggest when:
   - content is a long report, analysis, business plan, research
   - document needs a short, decision-oriented summary for management
   - action: "create an executive summary"

ac) Comparison table 📊 — suggest when:
   - content compares products, options, features, results
   - document contains numerical data to tabulate

ad) Action plan / Roadmap 🚩 — suggest when:
   - content describes goals, strategy, project plan, vision
   - document needs to be translated into concrete steps with deadlines
   - action: "create a step-by-step action plan"

ae) Email draft / Letter 📧 — suggest when:
   - content contains information requiring formal communication
   - document is a complaint, application, report, or requires a response
   - action: "write an email draft based on the content"

af) Cover letter / CV 💼 — suggest when:
   - content is a job offer, position description, recruitment requirements
   - document is a CV, portfolio, or application materials
   - action: "write a cover letter based on the job offer"

ag) Dialogue / Script 🎬 — suggest when:
   - content is about an interview, hearing, meeting, negotiation
   - document has dramatic or educational potential in dialogue form
   - action: "write a dialogue / script"

ah) Text infographic 📊 — suggest when:
   - content contains statistics, numerical data, facts to visualize
   - document is suitable for presenting key numbers and facts
   - action: "create a text infographic with the most important data"

ai) Song / Lyrics 🎵 — suggest when:
   - content is emotional, tells a story, has a rhyming character
   - document is about music, song lyrics, or has lyrical potential
   - action: "write an inspired song / lyrics"

aj) Translate content [language flag] — suggest when:
   - content is in a foreign language for the user (e.g. English document for a Polish user)
   - document contains fragments in different languages
   - action: "Translate to [language] [target language flag]" — use the TARGET LANGUAGE FLAG, NOT the globe 🌍. Examples: "Translate to English 🇬🇧", "Translate to Polish 🇵🇱", "Translate to German 🇩🇪", "Translate to French 🇫🇷"

ak) EXIF metadata 📷 — suggest ONLY when:
   - file is a photo (image) — never for PDF or text
   - file has practically no content (e.g. it is a PDF with 600 pages in Arabic for OCR, author Rumi who is a poet, but the document is only a scan of his manuscript with no textual data to analyze) — in that case suggest EXIF instead of content questions

al) Recognize person 🔍 — suggest ONLY when:
   - a person/human face is clearly visible in the photo
   - do NOT suggest for photos of landscapes, animals, objects
   - format: "Who is the woman/man/person in photo filename? 🔍"

am) Recipe 🍝 — suggest when:
   - photo shows ingredients or a finished dish
   - file is about cooking, baking bread, culinary recipes
   - food products are visible in the photo
Uploaded files: {file_types_str}
Document description: {description}""",
                ),
                ("human", "{content}"),
            ]
        )

    llm = get_llm()
    chain = prompt | llm | StrOutputParser()
    model = getattr(llm, "model", None) or getattr(llm, "model_name", None) or "unknown"
    params: dict = {"content": sample, "description": description, "file_types_str": _file_types_str}
    if language != "pl":
        params["output_language_name"] = _LANG_NAMES.get(language or "en", (language or "en").upper())
    response, _usage = traced_llm_call(
        chain=chain,
        params=params,
        operation="suggested_questions",
        model=model,
    )

    # Parse JSON response
    try:
        parsed = json.loads(response.strip())
        questions = parsed.get("questions", [])
        if isinstance(questions, list) and len(questions) >= 3:
            return _append_contextual_prompts(
                questions,
                file_names,
                file_types,
                language,
                welcome_message,
                description,
                page_count,
            )
    except (json.JSONDecodeError, AttributeError):
        logger.warning(
            "Failed to parse JSON from suggested questions response, falling back to line parsing"
        )

    # Fallback: parse as lines (backward compat)
    questions = [line.strip("- ").strip() for line in response.splitlines() if line.strip()]
    return _append_contextual_prompts(
        questions,
        file_names,
        file_types,
        language,
        welcome_message,
        description,
        page_count,
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
    r"contains|zawiera|nutrition|wartości odżywcze|product label|etykiet|"
    r"food|dish|dishes|meal|cuisine|buffet|restaurant|catering|cooked|fried|baked|"
    r"soup|salad|pastry|pastries|tray|plate|snack|snacks|cafeteria|canteen|appetizer|"
    r"potraw|potrawa|jedzenie|posiłek|bufet|kuchni|kuchnia|danie|dania|smażon|pieczon|"
    r"zupa|sałatk|taca|stołówk|talerz|przekąsk|placki|racuch|bielasz|jogurt|sos)\b",
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

# Documents that match _LAB_TEST_PATTERN incidentally but are not medical patient records
_NON_MEDICAL_CONTEXT_PATTERN = re.compile(
    r"\b(instrukcja obs\u0142ugi|podr\u0119cznik|encyklopedia|s\u0142ownik|powie\u015b\u0107|"
    r"powieści|beletrystyk|kryminał|thriller|romans|fantasy|scenariusz|"
    r"przepis|kucharsk|odkurzacz|zmywarka|pralka|lodówka|urządzeni[ae]|"
    r"manual|handbook|encyclopedia|dictionary|novel|fiction|recipe|cookbook|"
    r"appliance|vacuum.*cleaner|washing.*machine|dishwasher|user.*guide|"
    r"owner.*manual|technical.*manual|engineering|physics|chemistry|"
    r"history.*of|biography|autobiography)\b",
    re.IGNORECASE,
)

_FICTION_PATTERN = re.compile(
    r"\b(powieść|powieści|beletrystyka|kryminał|thriller|romans|fantasy|sci-fi|"
    r"horror|opowiadanie|opowieści|tom serii|seria|fabuła|bohater|akcja zaczyna|"
    r"novel|fiction|crime|mystery|romance|short stor|narrative|chapter|protagonist|"
    r"stronicow[ya])\b",
    re.IGNORECASE,
)

_POETRY_QUOTES_PATTERN = re.compile(
    r"\b(poezja|wiersz|wiersze|wiersza|cytaty?|aforyzmy?|sentencj[ae]|filozofi[ae]|"
    r"poet|poetry|poem|poems|quotes?|aphorism|philosophy|philosophical|"
    r"refleksj[ae]|medytacj[ae]|mądrości|przesłani[ae])\b",
    re.IGNORECASE,
)

_SELFHELP_PATTERN = re.compile(
    r"\b(poradnik|samorozwój|wskazówk[iae]|nawyk[iy]|produktywność|motywacj[ae]|"
    r"self.?help|personal.?growth|productivity|habit|confidence|mindset|"
    r"ćwiczeni[ae]|wyzwani[ae]|workbook|how.?to|tips?\b|advice|coaching)\b",
    re.IGNORECASE,
)

# Language-learning / language-teaching materials. Quiz is the single most valuable
# action for this type of content (practice & self-check), so when this matches the
# quiz prompt is pinned at the very top — even before the image prompt.
_LANGUAGE_LEARNING_PATTERN = re.compile(
    r"\b("
    # Polish phrasing
    r"nauka\s+(?:j\.\s*|języka\s+)?(?:angielski\w*|niemieck\w*|hiszpańsk\w*|francusk\w*|włosk\w*|"
    r"rosyjsk\w*|japońsk\w*|chińsk\w*|portugalsk\w*|obcego)|"
    r"(?:podręcznik|kurs|samouczek|repetytorium|ćwiczenia|lekcje)\s+(?:do\s+|z\s+|j\.\s*|języka\s+)"
    r"(?:angielsk\w*|niemieck\w*|hiszpańsk\w*|francusk\w*|włosk\w*)|"
    r"gramatyk[aąięey]\s+(?:angielsk\w*|niemieck\w*|hiszpańsk\w*|francusk\w*|włosk\w*)|"
    r"słownictw[oa]\s+(?:angielsk\w*|niemieck\w*|hiszpańsk\w*|francusk\w*|włosk\w*)|"
    # Standardised proficiency tests and ELT acronyms
    r"(?:ESL|EFL|ELT|TESOL|TOEFL|IELTS|CAE|FCE|CPE|CELTA)\b|"
    # English phrasing
    r"(?:english|german|spanish|french|italian|russian|japanese|chinese|portuguese|polish)\s+"
    r"(?:grammar|vocabulary|course|textbook|workbook|lesson|lessons|learner|learners|learning|"
    r"for\s+beginners|as\s+a\s+(?:second|foreign)\s+language)|"
    r"(?:learn(?:ing)?|teach(?:ing)?|study(?:ing)?|master(?:ing)?)\s+"
    r"(?:english|german|spanish|french|italian|russian|japanese|chinese|portuguese|polish)\b|"
    r"\blanguage\s+(?:course|textbook|learning|learner|acquisition|book|school)\b|"
    r"\b(?:foreign|second)\s+language\b"
    r")",
    re.IGNORECASE,
)

# Educational ebook / mini-book / textbook / subject-matter guide about a concrete topic.
# When content matches this (or the broader self-help pattern), the quiz action is pinned
# after generate-image and the creative "inspired chapter / poem / tips" prompt.
_EDUCATIONAL_EBOOK_PATTERN = re.compile(
    r"\b("
    r"ebook|e-book|minibook|mini-book|podręcznik|textbook|"
    r"(?:study|course|learning|teaching)\s+guide|course\s+material|lecture\s+notes|"
    r"lesson\s+plan|curriculum|edukacyjn[yaąe]|educational\s+(?:material|book|content|resource)|"
    r"introduction\s+to\s+\w+(?:\s+\w+){0,5}|wprowadzenie\s+do\s+\w+(?:\s+\w+){0,5}|"
    r"wszystko,?\s+co\s+musisz\s+wiedzieć|everything\s+you\s+(?:need|have)\s+to\s+know"
    r")\b",
    re.IGNORECASE,
)

_AUTHOR_FROM_STYLE_PATTERN = re.compile(
    r"(?:w stylu|like|inspired by|inspirowany?)\s+(.+?)(?:\s*[✏📜💡🏋🤔🎭📅]|$)",
    re.IGNORECASE,
)

# Precompiled helpers used in hot paths (see `_append_contextual_prompts`).
_QUIZ_KEYWORD_RE = re.compile(r"\bquiz\b", re.IGNORECASE)
_GRAMMAR_KEYWORD_RE = re.compile(r"\b(?:grammar|gramaty\w*)\b", re.IGNORECASE)
_VOCABULARY_KEYWORD_RE = re.compile(r"\b(?:vocabulary|słownictw\w*)\b", re.IGNORECASE)

# Matches "by Paulo Coelho" in descriptions/welcome messages.
# No re.IGNORECASE so [A-Z] truly means uppercase, preventing greedy capture of
# lowercase words that follow (e.g. "by Paulo Coelho follows Santiago" → "Paulo Coelho").
_AUTHOR_BY_PATTERN = re.compile(
    r"\bby\s+([A-Z][a-zA-Z\xC0-\xFF'\-]+(?:\s+[A-Z][a-zA-Z\xC0-\xFF'\-]+){0,2})"
)

# Detects school/job assignments, homework, exam questions, or any document that
# IS a task the user needs to complete. When matched, a "write the task result" action
# is pinned at the first visible slot (position 4) with the ✍️ emoji.
_SCHOOL_TASK_PATTERN = re.compile(
    r"\b("
    r"essay|assignment|homework|coursework|assessment|submission|task.?sheet|task\s+brief|"
    r"exam\s+(?:question|task|paper)|question(?:\s+paper)?|"
    r"[0-9]+\s*[-–—]\s*[0-9]+\s*words?|word\s*count|words\s*required|required\s*words|"
    r"marks?\s+will\s+be|deadline|due\s+date|submit\s+by|submission\s+date|"
    r"discuss\s+the|analyze\s+the|critically\s+anal|evaluate\s+the|examine\s+the|"
    r"wypracowanie|zadanie\s+domowe|esej|praca\s+domowa|referat|oddaj|termin\s+oddania"
    r")",
    re.IGNORECASE,
)


def _extract_task_word_count_and_type(text: str) -> tuple[str | None, str]:
    """Extract (word_count_string, task_type) from a school/job assignment document.

    Returns a word-count string like "1500-2000 words" or None if not found,
    plus the detected task type (essay, report, poem, etc.).
    """
    # Word count: "1500 – 2000 words", "500 words", "1,500 words"
    wc_range = re.search(
        r"([0-9][0-9,]*)\s*[-–—]\s*([0-9][0-9,]*)\s*words?", text, re.IGNORECASE
    )
    if wc_range:
        lo = wc_range.group(1).replace(",", "")
        hi = wc_range.group(2).replace(",", "")
        word_count: str | None = f"{lo}-{hi} words"
    else:
        wc_single = re.search(r"([0-9][0-9,]{2,})\s*words?", text, re.IGNORECASE)
        word_count = (
            f"{wc_single.group(1).replace(',', '')} words" if wc_single else None
        )

    # Task type — checked in priority order; first match wins
    type_patterns = [
        (r"\bdissertation\b|\bthesis\b", "dissertation"),
        (r"\breport\b", "report"),
        (r"\bcase\s+study\b", "case study"),
        (r"\bpresentation\b", "presentation"),
        (r"\bpoem\b|\bpoetry\b", "poem"),
        (r"\bchapter\b", "chapter"),
        (r"\breview\b|\bcritique\b", "review"),
        (r"\banalysis\b|\banalyze\b|\banalyse\b", "analysis"),
        (r"\bessay\b|\bwypracowanie\b|\besej\b", "essay"),
        (r"\breferat\b", "report"),
    ]
    for pattern, ttype in type_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return word_count, ttype

    return word_count, "essay"  # default fallback


def _is_valid_author_name(name: str) -> bool:
    """Return True if the extracted string looks like a real author name.

    Rejects:
    - Single-character initials ("P", "J.") that LLMs sometimes generate
    - Multi-word phrases containing lowercase words ("rozdział w stylu R")
    - Strings that are too long to be a name (> 4 words)
    """
    if not name or len(name) < 3:
        return False
    words = [w for w in name.split() if w]
    if len(words) > 4:
        return False
    # Every word must start with an uppercase letter — proper nouns only
    return all(w[0].isupper() for w in words)


def _extract_author_from_llm_actions(
    llm_actions: list[str],
    welcome_message: str,
) -> str | None:
    """Try to extract author name from LLM-generated action prompts or welcome message.

    Falls through each strategy in priority order, skipping any result that looks
    like a truncated initial (e.g. "P") rather than a real name.
    """
    # 1. Style pattern in LLM actions (e.g. "Write chapter like Paulo Coelho ✏️")
    for action in llm_actions:
        m = _AUTHOR_FROM_STYLE_PATTERN.search(action)
        if m:
            candidate = m.group(1).strip()
            if _is_valid_author_name(candidate):
                return candidate

    # 2. "Who is/was [Name]?" pattern in questions and welcome message
    who_pattern = re.compile(
        r"(?:Kim (?:jest|był[a]?)|Who (?:is|was))\s+(.+?)(?:\?|$)",
        re.IGNORECASE,
    )
    for text in llm_actions:
        m = who_pattern.search(text)
        if m:
            candidate = m.group(1).strip().rstrip("?")
            if _is_valid_author_name(candidate):
                return candidate
    m = who_pattern.search(welcome_message)
    if m:
        candidate = m.group(1).strip().rstrip("?")
        if _is_valid_author_name(candidate):
            return candidate

    # 3. "by [Author Name]" pattern in the description / welcome message — catches
    #    phrases like "This novel by Paulo Coelho..." when the LLM output is unhelpful.
    m = _AUTHOR_BY_PATTERN.search(welcome_message)
    if m:
        candidate = m.group(1).strip()
        if _is_valid_author_name(candidate):
            return candidate

    return None


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
        lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
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
    page_count: int | None = None,
) -> list[str]:
    """Build final list: up to 3 normal questions + up to 7 action prompts = max 10.

    Contextual action prompts (EXIF, recognize, file metadata) take priority
    over LLM-generated action prompts. 'recognize person name' is only added when
    the welcome message indicates a person is visible in the image.
    'create recipe' is added when the image description indicates ingredients,
    dishes, or other food-related context.

    For fiction books with 300+ pages, occasionally suggest 'write a large chapter inspired by'
    instead of or alongside 'write a chapter inspired by'.
    """
    # Split LLM output: first 3 are questions, next prompts are actions
    normal_questions = questions[:MAX_NORMAL_QUESTIONS]
    llm_actions = questions[MAX_NORMAL_QUESTIONS:MAX_TOTAL_SUGGESTED_PROMPTS]

    # Resolve the effective language for hardcoded action labels.
    # The passed `language` reflects the document language or the user's UI language.
    # When they differ (e.g. Arabic document + Polish UI), the LLM may generate questions
    # in the user's language even though `language` is "ar". Detect the actual output
    # language from the first 3 questions so hardcoded labels stay consistent with the
    # LLM-generated content.
    effective_language = language
    if language != "pl" and questions:
        detected_output = detect_language(" ".join(q for q in questions[:3] if q))
        if detected_output == "pl":
            effective_language = "pl"

    subject = _extract_subject_phrase(welcome_message, description, file_names, effective_language)
    pinned_image_prompt = (
        f"Wygeneruj obraz inspirowany: {subject} 🎨"
        if effective_language == "pl"
        else f"Generate an image inspired by: {subject} 🎨"
    )

    # Build contextual action prompts (higher priority than LLM actions).
    # Person / ingredient / lab-test detection scans both welcome_message AND
    # description because vision models often place the subject description
    # (e.g. "showing a woman in a white swimsuit") in the longer description
    # paragraph rather than the short welcome headline.
    detection_text = f"{welcome_message}\n{description}"
    contextual: list[str] = []
    has_lab_tests = bool(_LAB_TEST_PATTERN.search(detection_text))
    if file_names and file_types:
        has_person = bool(_PERSON_PATTERN.search(detection_text))
        is_woman = bool(_WOMAN_PATTERN.search(detection_text))
        is_man = bool(_MAN_PATTERN.search(detection_text))
        has_ingredients = bool(_INGREDIENT_PATTERN.search(detection_text))

        for name in file_names:
            if len(contextual) >= MAX_ACTION_PROMPTS:
                break
            ftype = file_types.get(name, "document")
            display_name = clean_file_name(name)
            short_name = display_name if len(display_name) <= 30 else display_name[:27] + "..."

            if ftype == "image":
                if has_ingredients and len(contextual) < MAX_ACTION_PROMPTS:
                    if effective_language == "pl":
                        contextual.append(f"Stwórz przepis inspirowany: {subject} 🍳")
                    else:
                        contextual.append(f"Create a recipe inspired by {subject} 🍳")
                if len(contextual) < MAX_ACTION_PROMPTS:
                    if effective_language == "pl":
                        contextual.append(f"Pokaż metadane EXIF dla {short_name} 📷")
                        if has_person and len(contextual) < MAX_ACTION_PROMPTS:
                            if is_woman:
                                contextual.append(f"Kto jest kobietą na zdjęciu {short_name}? 🔍")
                            elif is_man:
                                contextual.append(f"Kto jest mężczyzną na zdjęciu {short_name}? 🔍")
                            else:
                                contextual.append(f"Kto jest osobą na zdjęciu {short_name}? 🔍")
                    else:
                        contextual.append(f"Show EXIF metadata for {short_name} 📷")
                        if has_person and len(contextual) < MAX_ACTION_PROMPTS:
                            if is_woman:
                                contextual.append(f"Who is the woman in {short_name}? 🔍")
                            elif is_man:
                                contextual.append(f"Who is the man in {short_name}? 🔍")
                            else:
                                contextual.append(f"Who is the person in {short_name}? 🔍")
            # PDF metadata prompt removed — LLM-generated creative actions are more valuable

    # Lab test / blood test results → diagnosis prompt
    # Only inject when the document is genuinely medical patient data, not just any
    # document that happens to contain medical terminology (manuals, textbooks, etc.)
    is_non_medical = bool(_NON_MEDICAL_CONTEXT_PATTERN.search(welcome_message))
    if has_lab_tests and not is_non_medical and len(contextual) < MAX_ACTION_PROMPTS:
        if effective_language == "pl":
            contextual.insert(0, "Postaw diagnozę na podstawie wyników 🔬")
        else:
            contextual.insert(0, "Make a diagnosis based on results 🔬")

    # Detect content type from welcome message + description for pinned creative prompt
    combined_text = f"{welcome_message} {description}"
    author_name = _extract_author_from_llm_actions(
        questions, combined_text,
    )

    pinned_creative_prompt: str | None = None
    pinned_quote_prompt: str | None = None
    is_fiction = bool(_FICTION_PATTERN.search(combined_text))
    is_poetry_quotes = bool(_POETRY_QUOTES_PATTERN.search(combined_text))
    is_selfhelp = bool(_SELFHELP_PATTERN.search(combined_text))
    is_language_learning = bool(_LANGUAGE_LEARNING_PATTERN.search(combined_text))
    is_educational_ebook = bool(_EDUCATIONAL_EBOOK_PATTERN.search(combined_text))

    # School / job / homework / exam assignment — detected from document content.
    # The full document text (chunks joined) is checked as well so that assignments
    # without a rich welcome message (e.g. a 1-page PDF) are still caught.
    _chunks_text = " ".join(questions)  # questions carry document vocabulary
    is_school_task = bool(
        _SCHOOL_TASK_PATTERN.search(combined_text)
        or _SCHOOL_TASK_PATTERN.search(_chunks_text)
    )

    # For school tasks, extract the task type and word count so we can build a
    # "write the full task" action label at the first visible slot (position 4).
    pinned_task_prompt: str | None = None
    if is_school_task:
        _all_task_text = f"{combined_text} {_chunks_text}"
        _word_count, _task_type = _extract_task_word_count_and_type(_all_task_text)
        _subject_for_task = subject if len(subject) <= 40 else subject[:37] + "..."
        if _word_count:
            pinned_task_prompt = (
                f"Napisz {_task_type}: {_word_count} na temat: {_subject_for_task} ✍️"
                if effective_language == "pl"
                else f"Write {_task_type}: {_word_count} about {_subject_for_task} ✍️"
            )
        else:
            pinned_task_prompt = (
                f"Napisz {_task_type} na temat: {_subject_for_task} ✍️"
                if effective_language == "pl"
                else f"Write {_task_type} about {_subject_for_task} ✍️"
            )
        # School tasks should not trigger unrelated creative pinning
        pinned_creative_prompt = None

    # Threshold for "large" book: 300+ pages (e.g., J.K. Rowling novels)
    _IS_LARGE_BOOK = page_count and page_count >= 300

    if is_fiction and author_name:
        if _IS_LARGE_BOOK:
            # For large books, occasionally suggest "large chapter" to match the epic scope
            pinned_creative_prompt = (
                f"Napisz nowy inspirowany duży rozdział w stylu {author_name} ✏️"
                if effective_language == "pl"
                else f"Write a new large chapter inspired by {author_name} ✏️"
            )
        else:
            pinned_creative_prompt = (
                f"Napisz nowy inspirowany rozdział w stylu {author_name} ✏️"
                if effective_language == "pl"
                else f"Write a new chapter inspired by {author_name} ✏️"
            )
    elif is_poetry_quotes and author_name:
        pinned_creative_prompt = (
            f"Napisz nowy inspirowany wiersz w stylu {author_name} 📜"
            if effective_language == "pl"
            else f"Write a new poem inspired by {author_name} 📜"
        )
        pinned_quote_prompt = (
            f"Napisz nowy inspirowany cytat w stylu {author_name} 💬"
            if effective_language == "pl"
            else f"Write a new quote inspired by {author_name} 💬"
        )
    elif is_selfhelp and author_name:
        _selfhelp_options_pl = [
            f"Napisz 10 nowych wskazówek inspirowanych {author_name} 💡",
            f"Stwórz 7 ćwiczeń inspirowanych {author_name} 🏋️",
            f"Wygeneruj 12 pytań refleksyjnych inspirowanych {author_name} 🤔",
            f"Napisz 5 scenariuszy z życia inspirowanych {author_name} 🎭",
            f"Stwórz 14-dniowy plan działania inspirowany {author_name} 📅",
        ]
        _selfhelp_options_en = [
            f"Write 10 new tips inspired by {author_name} 💡",
            f"Create 7 exercises inspired by {author_name} 🏋️",
            f"Generate 12 reflection questions inspired by {author_name} 🤔",
            f"Draft 5 real-life scenarios inspired by {author_name} 🎭",
            f"Build a 14-day action plan inspired by {author_name} 📅",
        ]
        options = _selfhelp_options_pl if effective_language == "pl" else _selfhelp_options_en
        pinned_creative_prompt = random.choice(options)

    # Quiz pinning: educational ebooks / subject-matter guides benefit strongly from
    # a quiz action. We intentionally keep this scoped to educational content
    # (self-help guides, ebooks, minibooks, textbooks) — fiction novels and poetry
    # collections are not the target of this feature. Problem documents explicitly
    # prohibit creative content, but they never match the patterns below so they
    # are safe by construction. The language-learning branch is handled separately.
    generic_quiz_prompt = (
        "Stwórz quiz z najważniejszych faktów 🧠"
        if effective_language == "pl"
        else "Create a quiz from the key facts 🧠"
    )

    # For language-learning material, tailor the quiz prompt to the detected
    # sub-topic so the pinned action aligns with the updated prompt guidance
    # ("Create a vocabulary quiz", "Create a grammar quiz", etc.).
    def _language_learning_quiz_prompt() -> str:
        has_grammar = bool(_GRAMMAR_KEYWORD_RE.search(combined_text))
        has_vocabulary = bool(_VOCABULARY_KEYWORD_RE.search(combined_text))
        if effective_language == "pl":
            if has_grammar and not has_vocabulary:
                return "Stwórz quiz z gramatyki 🧠"
            if has_vocabulary and not has_grammar:
                return "Stwórz quiz ze słownictwa 🧠"
            return "Stwórz quiz z materiału 🧠"
        if has_grammar and not has_vocabulary:
            return "Create a grammar quiz 🧠"
        if has_vocabulary and not has_grammar:
            return "Create a vocabulary quiz 🧠"
        return "Create a quiz from the material 🧠"

    should_pin_quiz = (
        not is_language_learning
        and (is_educational_ebook or is_selfhelp)
    )

    # For educational ebooks / self-help without an author-dependent creative prompt,
    # fall back to a neutral creative action so the quiz still lands in the 3rd pinned
    # slot (matching the documented "image → inspired … → quiz" ordering).
    if (
        should_pin_quiz
        and pinned_creative_prompt is None
        and (is_educational_ebook or is_selfhelp)
    ):
        subject_for_creative = subject if len(subject) <= 45 else subject[:42] + "..."
        pinned_creative_prompt = (
            f"Napisz nowy inspirowany rozdział na podstawie: {subject_for_creative} ✏️"
            if effective_language == "pl"
            else f"Write a new chapter inspired by: {subject_for_creative} ✏️"
        )

    # Cross-language dialogue action: when the uploaded document is in a different
    # language than the user's current UI language (e.g. French exercises for an
    # English-speaking user), suggest creating a bilingual dialogue as the 3rd pinned
    # action. This is most valuable for language-learning or educational material.
    doc_lang_tag = _DOC_LANGUAGE_TAG_RE.search(welcome_message)
    doc_lang_code = doc_lang_tag.group(1).lower() if doc_lang_tag else None
    ui_lang = effective_language or "en"
    cross_lang_dialogue_prompt: str | None = None
    if doc_lang_code and doc_lang_code != ui_lang and (is_language_learning or is_educational_ebook):
        doc_lang_name = _LANG_NAMES.get(doc_lang_code, doc_lang_code.upper())
        ui_lang_name = _LANG_NAMES.get(ui_lang, ui_lang.upper())
        if effective_language == "pl":
            doc_loc = _LANG_PL_LOCATIVE.get(doc_lang_code, doc_lang_name)
            ui_loc = _LANG_PL_LOCATIVE.get(ui_lang, ui_lang_name)
            cross_lang_dialogue_prompt = f"Stwórz dialog po {doc_loc} i {ui_loc} 💬"
        else:
            cross_lang_dialogue_prompt = f"Create a dialogue in {doc_lang_name} and {ui_lang_name} 💬"

    if is_school_task and pinned_task_prompt:
        # School/job task: task writer first, image second — no quiz in visible slots.
        # The task writer action is the core of what the user needs (write the essay /
        # report / poem), so it takes priority over image generation.
        quiz_prompt = generic_quiz_prompt
        pinned = [pinned_task_prompt, pinned_image_prompt]
    elif is_language_learning:
        # Language-learning / teaching materials → quiz is the single most useful action,
        # so it takes the very first slot, ahead of the image prompt.
        quiz_prompt = _language_learning_quiz_prompt()
        pinned = [quiz_prompt, pinned_image_prompt]
        if cross_lang_dialogue_prompt:
            pinned.append(cross_lang_dialogue_prompt)
    else:
        quiz_prompt = generic_quiz_prompt
        pinned = [pinned_image_prompt]
        if pinned_creative_prompt:
            pinned.append(pinned_creative_prompt)
        if pinned_quote_prompt:
            pinned.append(pinned_quote_prompt)
        if should_pin_quiz:
            pinned.append(quiz_prompt)

    # Treat an action as quiz-related only when it shows quiz intent. The 🧠 emoji
    # alone is not enough, because unrelated "brainstorm"/"think" actions may also
    # use it.
    quiz_is_pinned = quiz_prompt in pinned
    if quiz_is_pinned:
        def _is_quiz_action(action: str) -> bool:
            stripped = action.lstrip()
            lowered = stripped.lower()
            has_quiz_keyword = _QUIZ_KEYWORD_RE.search(lowered) is not None
            starts_like_quiz = lowered.startswith(
                ("quiz", "stwórz quiz", "create a quiz", "create quiz")
            )
            return starts_like_quiz or ("🧠" in action and has_quiz_keyword)

        llm_actions = [a for a in llm_actions if not _is_quiz_action(a)]

    # When a pinned task-writer action is present, suppress any LLM-generated ✍️
    # actions so the user doesn't see two task-writer entries.
    if pinned_task_prompt:
        llm_actions = [a for a in llm_actions if "✍️" not in a]

    # Key facts: include for all text content; skip for image-only conversations
    has_text_content = not file_types or any(v != "image" for v in file_types.values())
    key_facts_prompt: str | None = (
        ("Napisz listę kluczowych faktów ☝️" if effective_language == "pl" else "Write a list of key facts ☝️")
        if has_text_content
        else None
    )

    actions = pinned + ([key_facts_prompt] if key_facts_prompt else []) + contextual + llm_actions

    # Build the final list with explicit caps per group:
    # - max 3 normal questions
    # - max 7 action prompts
    # This guarantees the action cap even after deduplication.
    deduped_normal: list[str] = []
    seen_normal: set[str] = set()
    for question in normal_questions:
        key = question.strip().lower()
        if key and key not in seen_normal:
            deduped_normal.append(question)
            seen_normal.add(key)
        if len(deduped_normal) >= MAX_NORMAL_QUESTIONS:
            break

    deduped_actions: list[str] = []
    seen_actions: set[str] = set()
    for action in actions:
        key = action.strip().lower()
        if key and key not in seen_actions:
            deduped_actions.append(action)
            seen_actions.add(key)
        if len(deduped_actions) >= MAX_ACTION_PROMPTS:
            break

    final = deduped_normal + deduped_actions
    # Defensive guard in case constants diverge in future refactors.
    return final[:MAX_TOTAL_SUGGESTED_PROMPTS]
