"""Extended tests for shared.lang_detect — exotic scripts and heuristics.

Extends the basic TestDetectLanguage suite with internal-function tests for
_dominant_exotic_script and _LANG_CHARS fast-path behaviour.
"""

from __future__ import annotations

from shared.lang_detect import _dominant_exotic_script, detect_language


class TestDominantExoticScript:
    """Tests for the unicode-script-range counter."""

    def test_pure_arabic_text(self):
        arabic = "مرحبا بالعالم هذا نص عربي"
        assert _dominant_exotic_script(arabic) == "ar"

    def test_pure_cyrillic_text(self):
        russian = "Привет мир это русский текст"
        assert _dominant_exotic_script(russian) == "ru"

    def test_pure_cjk_text(self):
        chinese = "你好世界这是中文文字"
        assert _dominant_exotic_script(chinese) == "zh"

    def test_hiragana_japanese(self):
        japanese = "こんにちは世界"
        result = _dominant_exotic_script(japanese)
        # Either ja (hiragana) or zh (CJK) is acceptable — depends on char distribution
        assert result in ("ja", "zh")

    def test_korean_hangul(self):
        korean = "안녕하세요 세계"
        assert _dominant_exotic_script(korean) == "ko"

    def test_devanagari_hindi(self):
        hindi = "नमस्ते दुनिया यह हिंदी पाठ है"
        assert _dominant_exotic_script(hindi) == "hi"

    def test_hebrew_text(self):
        hebrew = "שלום עולם זה טקסט עברי"
        assert _dominant_exotic_script(hebrew) == "he"

    def test_thai_text(self):
        thai = "สวัสดีชาวโลกนี่คือข้อความภาษาไทย"
        assert _dominant_exotic_script(thai) == "th"

    def test_pure_latin_returns_none(self):
        assert _dominant_exotic_script("Hello world, just plain English text!") is None

    def test_empty_string_returns_none(self):
        assert _dominant_exotic_script("") is None

    def test_mixed_latin_and_arabic_above_threshold(self):
        # ~20% Arabic chars mixed with Latin — should still detect "ar"
        latin_part = "Chapter One Introduction " * 3
        arabic_part = "مرحبا بالعالم "  # 14 Arabic chars
        mixed = latin_part + arabic_part
        result = _dominant_exotic_script(mixed)
        # 14 Arabic chars out of ~85 total = 16% → above 5% threshold
        assert result == "ar"

    def test_sparse_arabic_below_threshold_returns_none(self):
        # Very few Arabic chars in a large Latin text → below 5% threshold
        long_latin = "a" * 200
        one_arabic = "ا"  # 1 Arabic char
        mixed = long_latin + one_arabic
        result = _dominant_exotic_script(mixed)
        # 1/201 ≈ 0.5% → below threshold, should be None
        assert result is None


class TestDetectLanguageExtended:
    """Extended integration tests for the public detect_language function."""

    def test_arabic_text_detected(self):
        arabic = "مرحبا بالعالم، هذا نص عربي طويل بما يكفي"
        assert detect_language(arabic) == "ar"

    def test_russian_text_detected(self):
        russian = "Привет мир, это достаточно длинный русский текст"
        assert detect_language(russian) == "ru"

    def test_spanish_text_detected(self):
        assert detect_language("¡Hola mundo! ¿Cómo estás hoy?") == "es"

    def test_polish_diacritics_detected(self):
        assert detect_language("Ząb boli, weź tabletkę") == "pl"

    def test_whitespace_only_defaults_to_english(self):
        assert detect_language("   \n\t  ") == "en"

    def test_single_word_unicode_detected(self):
        # Single Arabic word — mostly exotic chars → "ar"
        result = detect_language("مرحبا")
        assert result == "ar"

    def test_chinese_text_detected(self):
        chinese = "你好世界，这是一段中文文字，用于测试语言检测功能"
        assert detect_language(chinese) == "zh"

    def test_mixed_arabic_with_latin_titles_detected_as_arabic(self):
        # Simulate an Arabic book page with English chapter heading
        text = "Chapter 1: Introduction\n" + "هذا هو المحتوى الرئيسي للكتاب العربي " * 5
        assert detect_language(text) == "ar"

    def test_german_special_chars(self):
        assert detect_language("Das ist ein Satz mit Umlaut: äöüß") == "de"

    def test_french_special_chars(self):
        text = "C'est une phrase française avec des accents: éèêâ"
        assert detect_language(text) == "fr"
