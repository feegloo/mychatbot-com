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

    assert len(result) >= 6
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

    assert len(result) >= 6
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
    assert len(result) >= 6
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
