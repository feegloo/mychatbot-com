from langdetect import DetectorFactory
from langdetect import detect as _langdetect_detect
from langdetect import detect_langs as _langdetect_detect_langs

DetectorFactory.seed = 0  # for reproducibility

# Character sets for fast heuristic detection of common languages.
# Avoids the ~3s langdetect profile-loading penalty for the typical case.
_LANG_CHARS = {
    "pl": set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ"),
    "de": set("äöüßÄÖÜ"),
    "fr": set("àâæçéèêëîïôœùûüÿÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ"),
    "es": set("ñ¿¡Ñ"),
}

# Unicode script ranges for "exotic" (non-Latin) scripts that should take
# priority over English when both appear in the same document (e.g. an Arabic
# book that has an English table-of-contents page, or a Mathnawi scan with
# English chapter headings).
_EXOTIC_SCRIPT_RANGES: list[tuple[int, int, str]] = [
    (0x0600, 0x06FF, "ar"),   # Arabic
    (0x0750, 0x077F, "ar"),   # Arabic Supplement
    (0xFB50, 0xFDFF, "ar"),   # Arabic Presentation Forms-A
    (0xFE70, 0xFEFF, "ar"),   # Arabic Presentation Forms-B
    (0x0400, 0x04FF, "ru"),   # Cyrillic
    (0x0500, 0x052F, "ru"),   # Cyrillic Supplement
    (0x4E00, 0x9FFF, "zh"),   # CJK Unified Ideographs (Chinese/Japanese/Korean)
    (0x3040, 0x309F, "ja"),   # Hiragana
    (0x30A0, 0x30FF, "ja"),   # Katakana
    (0xAC00, 0xD7AF, "ko"),   # Hangul Syllables
    (0x0900, 0x097F, "hi"),   # Devanagari (Hindi/Sanskrit)
    (0x0E00, 0x0E7F, "th"),   # Thai
    (0x0590, 0x05FF, "he"),   # Hebrew
    (0x0980, 0x09FF, "bn"),   # Bengali
]


def _dominant_exotic_script(sample: str) -> str | None:
    """Return the dominant exotic-script language if it has enough presence.

    Counts code-points falling into each exotic unicode block.  If the top
    script accounts for at least 5 % of the sample, it wins — even when
    English words are also present.  This handles mixed-language documents
    like Arabic books with English chapter headings.
    """
    counts: dict[str, int] = {}
    for ch in sample:
        cp = ord(ch)
        for lo, hi, lang in _EXOTIC_SCRIPT_RANGES:
            if lo <= cp <= hi:
                counts[lang] = counts.get(lang, 0) + 1
                break

    if not counts:
        return None

    top_lang, top_count = max(counts.items(), key=lambda kv: kv[1])
    ratio = top_count / max(len(sample), 1)
    # 5 % threshold: a scanned Arabic book where OCR picks up some Latin
    # characters will still be correctly identified as Arabic.
    if ratio >= 0.05:
        return top_lang
    return None


def detect_language(text: str) -> str:
    """Detect language with exotic-script priority over English.

    Detection order:
    1. Check for exotic non-Latin scripts (Arabic, CJK, Cyrillic, etc.).
       If a script covers ≥5 % of the sample, that language wins — even if
       English words are also present.  This prevents bilingual documents
       (e.g. "Mathnawi Rumi" with English headings) from being mis-labelled
       as English.
    2. Fast diacritic heuristic for accented Latin scripts (Polish, German …).
    3. Short-circuit to English for nearly pure ASCII text.
    4. langdetect statistical fallback for everything else.
    """
    sample = text[:2000]

    # 1. Exotic / non-Latin script dominance check (highest priority)
    exotic = _dominant_exotic_script(sample)
    if exotic:
        return exotic

    # 2. Fast path: check for language-specific diacritics
    for lang, chars in _LANG_CHARS.items():
        if sum(1 for c in sample if c in chars) >= 3:
            return lang

    # 3. If text is mostly ASCII, it's very likely English
    non_ascii = sum(1 for c in sample if ord(c) > 127)
    if len(sample) > 0 and non_ascii < len(sample) * 0.05:
        return "en"

    # 4. Fallback to full statistical detection for other languages
    try:
        return _langdetect_detect(text)
    except Exception:
        return "en"
