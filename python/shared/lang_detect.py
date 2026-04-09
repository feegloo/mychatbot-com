from langdetect import detect as _langdetect_detect, DetectorFactory

DetectorFactory.seed = 0  # for reproducibility

# Character sets for fast heuristic detection of common languages.
# Avoids the ~3s langdetect profile-loading penalty for the typical case.
_LANG_CHARS = {
    'pl': set('ąćęłńóśźżĄĆĘŁŃÓŚŹŻ'),
    'de': set('äöüßÄÖÜ'),
    'fr': set('àâæçéèêëîïôœùûüÿÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ'),
    'es': set('ñ¿¡Ñ'),
}


def detect_language(text: str) -> str:
    """Detect language: fast character heuristic, with langdetect fallback."""
    sample = text[:1000]

    # Fast path: check for language-specific diacritics
    for lang, chars in _LANG_CHARS.items():
        if sum(1 for c in sample if c in chars) >= 3:
            return lang

    # If text is mostly ASCII, it's very likely English
    non_ascii = sum(1 for c in sample if ord(c) > 127)
    if len(sample) > 0 and non_ascii < len(sample) * 0.05:
        return 'en'

    # Fallback to full statistical detection for other languages
    try:
        return _langdetect_detect(text)
    except Exception:
        return 'en'
