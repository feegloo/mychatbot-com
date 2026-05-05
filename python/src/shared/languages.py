"""ISO 639-1 code → English name mapping shared across modules.

Kept in its own tiny module so that ``rag.py`` and other modules on the
answer/query path can import just this dict without pulling in the large
prompt-string constants in ``prompts/welcome.py``.
"""

LANG_NAMES: dict[str, str] = {
    "en": "English", "pl": "Polish", "de": "German", "fr": "French",
    "es": "Spanish", "it": "Italian", "pt": "Portuguese", "nl": "Dutch",
    "ru": "Russian", "uk": "Ukrainian", "cs": "Czech", "sk": "Slovak",
    "hu": "Hungarian", "ro": "Romanian", "bg": "Bulgarian", "hr": "Croatian",
    "sl": "Slovenian", "sr": "Serbian", "el": "Greek", "tr": "Turkish",
    "ar": "Arabic", "he": "Hebrew", "hi": "Hindi", "fa": "Persian",
    "ur": "Urdu", "bn": "Bengali", "zh": "Chinese", "ja": "Japanese",
    "ko": "Korean", "vi": "Vietnamese", "th": "Thai", "id": "Indonesian",
    "ms": "Malay", "sv": "Swedish", "da": "Danish", "fi": "Finnish",
    "no": "Norwegian", "lt": "Lithuanian", "lv": "Latvian", "et": "Estonian",
}
