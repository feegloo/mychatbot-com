from langdetect import detect, DetectorFactory

DetectorFactory.seed = 0  # for reproducibility

def detect_language(text: str) -> str:
    """
    Detects the language of the given text and returns ISO 639-1 code (e.g., 'en', 'pl').
    """
    try:
        return detect(text)
    except Exception:
        return 'en'  # fallback to English if detection fails
