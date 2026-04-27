from shared.suggested_questions import _append_contextual_prompts, _extract_subject_phrase

# ---------------------------------------------------------------------------
# _extract_subject_phrase
# ---------------------------------------------------------------------------


def test_extract_subject_uses_markdown_heading():
    msg = "## Joanna Chyłka — Zaginięcie\n\nPowieść kryminalna Remigiusza Mroza."
    assert _extract_subject_phrase(msg, "", None, "pl") == "Joanna Chyłka — Zaginięcie"


def test_extract_subject_strips_bold_from_heading():
    msg = "## **Introduction to Tableau**\n\nLearn data visualisation."
    assert _extract_subject_phrase(msg, "", None, "en") == "Introduction to Tableau"


def test_extract_subject_truncates_long_heading():
    long_title = "A" * 60
    msg = f"## {long_title}"
    result = _extract_subject_phrase(msg, "", None, "en")
    assert result.endswith("...")
    assert len(result) <= 50


def test_extract_subject_falls_back_to_first_line():
    msg = "This is about machine learning and neural networks."
    result = _extract_subject_phrase(msg, "", None, "en")
    assert "machine learning" in result


def test_extract_subject_falls_back_to_file_name():
    result = _extract_subject_phrase("", "", ["my_report.pdf"], "en")
    assert "my_report" in result.lower()


def test_extract_subject_generic_fallback_en():
    assert _extract_subject_phrase("", "", None, "en") == "this content"


def test_extract_subject_generic_fallback_pl():
    assert _extract_subject_phrase("", "", None, "pl") == "tej treści"


def test_extract_subject_uses_description_when_welcome_has_no_heading():
    """description is searched when welcome_message has no usable heading."""
    welcome = "File was uploaded successfully."
    desc = "## Neural Networks Explained\n\nA deep dive."
    result = _extract_subject_phrase(welcome, desc, None, "en")
    assert result == "Neural Networks Explained"


def test_extract_subject_welcome_heading_takes_priority_over_description():
    """welcome_message heading wins even when description also has a heading."""
    welcome = "## Cooking Basics\n\nSimple recipes."
    desc = "## Advanced Patisserie\n\nComplex desserts."
    assert _extract_subject_phrase(welcome, desc, None, "en") == "Cooking Basics"


# ---------------------------------------------------------------------------
# _append_contextual_prompts — slot math and pinned image prompt
# ---------------------------------------------------------------------------


def test_pins_subject_image_prompt_with_correct_slot_math_english():
    result = _append_contextual_prompts(
        questions=[
            "What is this document about?",
            "What are the key findings?",
            "What should I do first?",
            "Create a quiz from the key facts 🧠",
            "Create study notes 📓",
        ],
        file_names=None,
        file_types=None,
        language="en",
        welcome_message="## Machine Learning Basics\n\nAn intro guide.",
    )

    assert 6 <= len(result) <= 10
    # Pinned image prompt occupies the 4th slot (after 3 questions)
    assert result[3] == "Generate image inspired by: Machine Learning Basics 🎨"
    assert sum(1 for q in result if "Generate image inspired by:" in q) == 1


def test_pins_subject_image_prompt_with_correct_slot_math_polish():
    result = _append_contextual_prompts(
        questions=[
            "O czym jest dokument?",
            "Jakie są kluczowe wnioski?",
            "Co zrobić najpierw?",
            "Stwórz quiz z najważniejszych faktów 🧠",
            "Stwórz notatki do nauki 📓",
        ],
        file_names=["foto.jpg"],
        file_types={"foto.jpg": "image"},
        language="pl",
        welcome_message="## Kuchnia polska\n\nPrzepisy i tradycje.",
    )

    assert 6 <= len(result) <= 10
    assert result[3] == "Wygeneruj obraz inspirowany: Kuchnia polska 🎨"
    assert sum(1 for q in result if "Wygeneruj obraz inspirowany:" in q) == 1


def test_contextual_action_not_dropped_when_present():
    """Contextual actions should be preserved in the expanded action set."""
    result = _append_contextual_prompts(
        questions=[
            "Q1", "Q2", "Q3", "LLM action A 🧠", "LLM action B 📓"
        ],
        file_names=["scan.jpg"],
        file_types={"scan.jpg": "image"},
        language="en",
        welcome_message="## Blood Test Results\n\nCholesterol and CBC results.",
    )
    assert 6 <= len(result) <= 10
    # Diagnosis contextual prompt must appear (not be dropped)
    assert any("diagnosis" in q.lower() for q in result)
    # Pinned image prompt must also appear
    assert any("Generate image inspired by:" in q for q in result)


def test_recognize_person_prompt_detected_from_description_body():
    """When welcome_message is terse (just a filename/title) but description
    describes a woman, the 'Who is the woman in ...' contextual prompt must
    still appear. Regression for prompts not surfacing on image portraits."""
    result = _append_contextual_prompts(
        questions=[
            "What is shown in this image?",
            "How is the subject posed?",
            "What does the indoor setting suggest?",
            "Assess the image quality 🔎",
            "Create a caption for this photo 📝",
            "Write a short image analysis report 📊",
            "Suggest improvements for the framing 🎯",
        ],
        file_names=["portrait.jpeg"],
        file_types={"portrait.jpeg": "image"},
        language="en",
        welcome_message="EuroGirlsEscorts",
        description=(
            "This JPEG is a simple indoor portrait at 359x532 px showing a "
            "woman standing in a white one-piece swimsuit against an interior "
            "background."
        ),
    )
    assert any(q.startswith("Who is the woman in") and "🔍" in q for q in result)


def test_generic_fallback_when_no_context():
    result = _append_contextual_prompts(
        questions=["Q1", "Q2", "Q3", "Action A 🧠", "Action B 📓"],
        file_names=None,
        file_types=None,
        language="en",
        welcome_message="",
    )
    assert any("Generate image inspired by: this content 🎨" in q for q in result)


def test_action_cap_is_enforced_after_dedup():
    """Duplicate normal prompts must not allow more than 7 actions in final output."""
    result = _append_contextual_prompts(
        questions=[
            "Repeat?",
            "Repeat?",
            "Repeat?",
            "Action 1 🧠",
            "Action 2 📓",
            "Action 3 📊",
            "Action 4 🖼️",
            "Action 5 🎯",
            "Action 6 📅",
            "Action 7 💡",
            "Action 8 🎨",
            "Action 9 🧩",
        ],
        file_names=None,
        file_types=None,
        language="en",
        welcome_message="## Topic",
    )

    # With duplicated normal prompts, final output should still respect:
    # - max 1 deduped normal prompt here ("Repeat?")
    # - max 7 action prompts
    assert len(result) <= 8
    assert any("Generate image inspired by:" in q for q in result)


# ---------------------------------------------------------------------------
# _extract_author_from_llm_actions — regression tests for name truncation
# ---------------------------------------------------------------------------


from shared.suggested_questions import _extract_author_from_llm_actions, _is_valid_author_name


def test_extract_author_falls_through_single_char_abbreviation():
    """When LLM abbreviates 'Paulo Coelho' to 'P', the who-pattern fallback
    should recover the full name from the questions list."""
    questions = [
        "What is Santiago's Personal Legend?",
        "Who is Paulo Coelho?",
        "How does Fatima affect Santiago's journey?",
        "Write inspired chapter like P \u270f\ufe0f",
    ]
    welcome = "This 136-page novel by Paulo Coelho follows Santiago..."
    result = _extract_author_from_llm_actions(questions, welcome)
    assert result == "Paulo Coelho"


def test_extract_author_full_name_in_action():
    """When LLM generates the full name in the action, it is returned directly."""
    questions = [
        "What is Santiago's Personal Legend?",
        "Write inspired chapter like Paulo Coelho \u270f\ufe0f",
    ]
    welcome = "This 136-page novel by Paulo Coelho follows Santiago..."
    result = _extract_author_from_llm_actions(questions, welcome)
    assert result == "Paulo Coelho"


def test_extract_author_by_pattern_fallback():
    """Falls back to 'by [Name]' pattern in welcome message when LLM provides no action."""
    questions = ["What is Santiago's Personal Legend?"]
    welcome = "This 136-page novel by Paulo Coelho follows Santiago..."
    result = _extract_author_from_llm_actions(questions, welcome)
    assert result == "Paulo Coelho"


def test_is_valid_author_name_rejects_single_char():
    assert _is_valid_author_name("P") is False
    assert _is_valid_author_name("J.") is False
    assert _is_valid_author_name("") is False


def test_is_valid_author_name_accepts_real_names():
    assert _is_valid_author_name("Paulo Coelho") is True
    assert _is_valid_author_name("Stephen King") is True
    assert _is_valid_author_name("J.K. Rowling") is True


def test_is_valid_author_name_rejects_mixed_case_phrase():
    # "rozdział w stylu R" must not be treated as an author name
    assert _is_valid_author_name("rozdział w stylu R") is False


# ---------------------------------------------------------------------------
# Quiz pinning — educational ebooks & language-learning materials
# ---------------------------------------------------------------------------


def test_quiz_pinned_as_third_action_for_educational_ebook_pl():
    """Minibook/ebook about a concrete subject → quiz appears as the 3rd pinned action,
    right after the generate-image prompt and the creative "inspired chapter" prompt.
    Screenshot scenario: 'Minibook o granicach' by Matylda Kozakiewicz."""
    welcome = (
        "## Minibook o granicach\n\n"
        "Minibook autorstwa Matyldy Kozakiewicz — poradnik i ebook o zdrowym "
        "stawianiu granic. Wszystko, co musisz wiedzieć o granicach w relacjach."
    )
    result = _append_contextual_prompts(
        questions=[
            "O czym jest ten minibook?",
            "Jak Matylda Kozakiewicz definiuje granice?",
            "Kim jest Matylda Kozakiewicz?",
            "Stwórz oś czasu wydarzeń 📅",
            "Napisz post na LinkedIn 📱",
        ],
        file_names=["Minibook-o-granicach.pdf"],
        file_types={"Minibook-o-granicach.pdf": "document"},
        language="pl",
        welcome_message=welcome,
    )

    # First 3 are the natural questions
    assert result[:3] == [
        "O czym jest ten minibook?",
        "Jak Matylda Kozakiewicz definiuje granice?",
        "Kim jest Matylda Kozakiewicz?",
    ]
    # 4th slot: pinned image prompt
    assert result[3].startswith("Wygeneruj obraz inspirowany:")
    # 5th slot: creative "inspired" prompt (chapter, tips, exercises, etc.)
    assert "Matyld" in result[4]
    # 6th slot: pinned quiz
    assert result[5] == "Stwórz quiz z najważniejszych faktów 🧠"


def test_quiz_pinned_first_for_language_learning_book_en():
    """English-language textbook → quiz is the TOP action, even before the image prompt."""
    welcome = (
        "## English Grammar for Beginners\n\n"
        "A textbook for learners of English as a second language — vocabulary, "
        "grammar exercises, and reading practice."
    )
    result = _append_contextual_prompts(
        questions=[
            "What topics are covered?",
            "Which grammar points are explained?",
            "What level is this book for?",
            "Create study notes 📓",
            "Create flashcards 🃏",
        ],
        file_names=["english-grammar.pdf"],
        file_types={"english-grammar.pdf": "document"},
        language="en",
        welcome_message=welcome,
    )

    # First 3 are natural questions
    assert result[:3] == [
        "What topics are covered?",
        "Which grammar points are explained?",
        "What level is this book for?",
    ]
    # 4th slot (first action) MUST be a quiz — ahead of the image prompt. The EN
    # welcome mentions both "grammar" and "vocabulary", so the generic
    # "material" variant is selected.
    assert result[3] == "Create a quiz from the material 🧠"
    # Image prompt follows in 5th slot
    assert result[4].startswith("Generate image inspired by:")


def test_quiz_pinned_first_for_language_learning_book_pl():
    """Polish-language textbook for learning a foreign language → quiz is first."""
    welcome = (
        "## Podręcznik do angielskiego\n\n"
        "Kurs języka angielskiego dla początkujących. Nauka angielskiego z "
        "ćwiczeniami gramatycznymi i słownictwem."
    )
    result = _append_contextual_prompts(
        questions=[
            "Jakie tematy są omówione?",
            "Jaki poziom prezentuje książka?",
            "Dla kogo jest przeznaczona?",
            "Stwórz fiszki 🃏",
            "Stwórz notatki 📓",
        ],
        file_names=["angielski.pdf"],
        file_types={"angielski.pdf": "document"},
        language="pl",
        welcome_message=welcome,
    )

    # PL welcome mentions both "gramatycznymi" (→ grammar) and "słownictwem"
    # (→ vocabulary), so the generic "materiału" variant is selected.
    assert result[3] == "Stwórz quiz z materiału 🧠"
    assert result[4].startswith("Wygeneruj obraz inspirowany:")


def test_language_learning_quiz_prompt_specialises_to_vocabulary():
    """When only vocabulary keywords are present, the pinned quiz uses the
    vocabulary variant — aligning with the updated PL/EN prompt guidance."""
    welcome = (
        "## English Vocabulary for Intermediate Learners\n\n"
        "A workbook to expand your English vocabulary with themed lessons."
    )
    result = _append_contextual_prompts(
        questions=["Q1", "Q2", "Q3", "Action 📓", "Action 🃏"],
        file_names=None,
        file_types=None,
        language="en",
        welcome_message=welcome,
    )
    assert result[3] == "Create a vocabulary quiz 🧠"


def test_language_learning_quiz_prompt_specialises_to_grammar_pl():
    """When only grammar keywords are present (PL), the pinned quiz uses the
    grammar variant."""
    welcome = (
        "## Gramatyka hiszpańska\n\n"
        "Podręcznik do nauki hiszpańskiego — omawia gramatykę i reguły składniowe."
    )
    result = _append_contextual_prompts(
        questions=["P1", "P2", "P3", "Akcja 📓", "Akcja 🃏"],
        file_names=None,
        file_types=None,
        language="pl",
        welcome_message=welcome,
    )
    assert result[3] == "Stwórz quiz z gramatyki 🧠"


def test_educational_ebook_without_author_keeps_quiz_at_third_slot():
    """Educational ebook that matches neither the fiction/poetry/self-help
    with-author branches still has the quiz pinned in the 3rd action slot
    (via a non-author creative fallback)."""
    welcome = (
        "## Introduction to Social Psychology\n\n"
        "An educational ebook / textbook covering the foundations of social psychology."
    )
    result = _append_contextual_prompts(
        questions=[
            "What does this textbook cover?",
            "Which schools of thought are discussed?",
            "How is the material structured?",
            "Create study notes 📓",
            "Draw a mind map 🧩",
        ],
        file_names=["intro-social-psych.pdf"],
        file_types={"intro-social-psych.pdf": "document"},
        language="en",
        welcome_message=welcome,
    )
    # 4th slot: image prompt
    assert result[3].startswith("Generate image inspired by:")
    # 5th slot: non-author creative fallback prompt (inspired chapter based on subject)
    assert "inspired chapter based on" in result[4].lower()
    # 6th slot: quiz — still 3rd of the pinned actions, not 2nd
    assert result[5] == "Create a quiz from the key facts 🧠"


def test_educational_ebook_multi_word_introduction_title_is_detected():
    """Regression: `introduction to social psychology` (multi-word subject)
    must satisfy `_EDUCATIONAL_EBOOK_PATTERN` so the quiz gets pinned."""
    from shared.suggested_questions import _EDUCATIONAL_EBOOK_PATTERN
    assert _EDUCATIONAL_EBOOK_PATTERN.search("Introduction to Social Psychology")
    assert _EDUCATIONAL_EBOOK_PATTERN.search("Wprowadzenie do psychologii społecznej")


def test_quiz_dedup_spares_brainstorm_actions_with_brain_emoji():
    """🧠 alone (without a 'quiz' keyword) must not be enough to drop an LLM
    action — otherwise brainstorm/think prompts get wiped when we pin a quiz."""
    welcome = "## Minibook o nawykach\n\nEbook o produktywności i samorozwoju."
    result = _append_contextual_prompts(
        questions=[
            "O czym jest minibook?",
            "Jakie nawyki są omówione?",
            "Dla kogo jest?",
            "Burza mózgów: nowe nawyki 🧠",  # brainstorm, not a quiz — must survive
            "Napisz post 📱",
        ],
        file_names=None,
        file_types=None,
        language="pl",
        welcome_message=welcome,
    )
    assert "Burza mózgów: nowe nawyki 🧠" in result, (
        f"Brainstorm action was incorrectly dropped by quiz dedup: {result}"
    )
    # Exactly one quiz must remain (the pinned one)
    assert sum(1 for q in result if "quiz" in q.lower()) == 1


def test_quiz_not_pinned_for_fiction_novel():
    """Fiction novels are outside the educational scope of this feature — we must
    NOT inject a quiz for them. They still get the existing image + inspired-chapter
    pins from the pre-existing logic."""
    welcome = (
        "## A Game of Thrones\n\n"
        "A novel by George R. R. Martin — fantasy series, chapter one, protagonist..."
    )
    result = _append_contextual_prompts(
        questions=[
            "What is this novel about?",
            "Who is the protagonist?",
            "Who is George R. R. Martin?",
            "Create a mind map 🧩",
            "Create a timeline 📅",
        ],
        file_names=["got.pdf"],
        file_types={"got.pdf": "document"},
        language="en",
        welcome_message=welcome,
    )

    # Image prompt pinned in slot 4 (first action), inspired-chapter in slot 5,
    # but our new quiz pin must NOT fire for fiction.
    assert result[3].startswith("Generate image inspired by:")
    assert "inspired chapter" in result[4].lower()
    assert not any(
        q == "Create a quiz from the key facts 🧠" for q in result
    ), f"Fiction must not get the pinned quiz prompt, got: {result}"


def test_quiz_not_pinned_for_problem_document():
    """Problem documents (ZUS, wezwania etc.) must not get a creative quiz prompt
    injected — they don't match any of our content-type patterns."""
    welcome = (
        "## Wezwanie do zapłaty\n\n"
        "Pismo z ZUS w sprawie zaległości składek. Termin odpowiedzi 14 dni."
    )
    result = _append_contextual_prompts(
        questions=[
            "Jaki jest termin na odpowiedź?",
            "Co dokładnie muszę złożyć?",
            "Czy mogę odwołać się?",
            "Lista kroków do rozwiązania problemu ✅",
            "Napisz odpowiedź na to pismo 📝",
        ],
        file_names=["wezwanie.pdf"],
        file_types={"wezwanie.pdf": "document"},
        language="pl",
        welcome_message=welcome,
    )

    assert not any(
        "quiz" in q.lower() for q in result
    ), f"Problem document should not have a quiz pinned, got: {result}"


def test_llm_generated_quiz_deduplicated_when_pinned():
    """When we pin our own quiz prompt, a near-duplicate quiz action from the LLM
    should be filtered out so users don't see two quiz entries."""
    welcome = "## Minibook o nawykach\n\nEbook o produktywności i samorozwoju."
    result = _append_contextual_prompts(
        questions=[
            "O czym jest minibook?",
            "Jakie nawyki są omówione?",
            "Dla kogo jest?",
            "Stwórz quiz ze szczegółów 🧠",  # LLM-generated quiz — should be filtered
            "Stwórz oś czasu 📅",
            "Napisz post 📱",
        ],
        file_names=["nawyki.pdf"],
        file_types={"nawyki.pdf": "document"},
        language="pl",
        welcome_message=welcome,
    )

    quiz_count = sum(1 for q in result if "quiz" in q.lower())
    assert quiz_count == 1, f"Expected exactly 1 quiz prompt, got {quiz_count}: {result}"
