import pytest
from shared.lang_detect import detect_language


class TestDetectLanguage:
    def test_english_text(self):
        assert detect_language("This is a simple English sentence for testing.") == "en"

    def test_polish_text(self):
        assert detect_language("Zażółć gęślą jaźń, to jest polski tekst.") == "pl"

    def test_german_text(self):
        assert detect_language("Das Mädchen läuft über die Straße nach Hause.") == "de"

    def test_french_text(self):
        assert detect_language("Ça fait longtemps que je n'ai pas mangé de crêpes.") == "fr"

    def test_empty_string_defaults_to_english(self):
        assert detect_language("") == "en"

    def test_ascii_text_is_english(self):
        assert detect_language("Hello world, this is a test.") == "en"
