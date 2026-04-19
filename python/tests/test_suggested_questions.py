from shared.suggested_questions import _append_contextual_prompts


def test_pins_mood_image_prompt_first_in_english():
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
        welcome_message="",
    )

    assert len(result) == 5
    assert result[0] == "Generate image for current mood 🎨"
    assert result.count("Generate image for current mood 🎨") == 1


def test_pins_mood_image_prompt_first_in_polish():
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
        welcome_message="Na zdjęciu są składniki i osoba",
    )

    assert len(result) == 5
    assert result[0] == "Wygeneruj obraz dla aktualnego nastroju 🎨"
    assert result.count("Wygeneruj obraz dla aktualnego nastroju 🎨") == 1
