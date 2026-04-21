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
