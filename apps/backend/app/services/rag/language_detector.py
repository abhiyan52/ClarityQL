"""Language detection utilities for RAG ingestion.

Supports multiple languages (EN, ES, HI, and more) for language-aware chunking.
"""

import logging
from typing import Optional
from langdetect import detect, LangDetectException

logger = logging.getLogger(__name__)

# Supported languages (ISO 639-1 codes)
SUPPORTED_LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "hi": "Hindi",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "zh-cn": "Chinese (Simplified)",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
}

DEFAULT_LANGUAGE = "en"


def detect_language(text: str, fallback: str = DEFAULT_LANGUAGE) -> str:
    """
    Detect the language of a text string.

    Uses langdetect library for fast, accurate detection.
    Falls back to default language if detection fails.

    Args:
        text: Text to detect language for.
        fallback: Fallback language code if detection fails.

    Returns:
        ISO 639-1 language code (e.g., 'en', 'es', 'hi').

    Example:
        >>> detect_language("This is an English sentence.")
        'en'
        >>> detect_language("Este es un texto en español.")
        'es'
    """
    if not text or not text.strip():
        return fallback

    try:

        # Detect language
        detected = detect(text)

        # Normalize (langdetect returns lowercase codes)
        detected = detected.lower()

        # Validate it's supported
        if detected in SUPPORTED_LANGUAGES:
            logger.debug(f"Detected language: {detected} ({SUPPORTED_LANGUAGES[detected]})")
            return detected

        # Check if it's a variant we can map
        detected = normalize_language_code(detected)

        if detected in SUPPORTED_LANGUAGES:
            return detected

        logger.warning(
            f"Detected language '{detected}' not in supported list. "
            f"Using fallback: {fallback}"
        )
        return fallback

    except LangDetectException as e:
        logger.warning(f"Language detection failed: {e}. Using fallback: {fallback}")
        return fallback
    except ImportError:
        logger.warning(
            "langdetect not installed. Using fallback language. "
            "Install with: pip install langdetect"
        )
        return fallback
    except Exception as e:
        logger.error(f"Unexpected error in language detection: {e}")
        return fallback


def detect_language_with_confidence(
    text: str,
    fallback: str = DEFAULT_LANGUAGE,
    min_confidence: float = 0.8,
) -> tuple[str, float]:
    """
    Detect language with confidence score.

    Args:
        text: Text to detect language for.
        fallback: Fallback language if confidence too low.
        min_confidence: Minimum confidence threshold (0.0-1.0).

    Returns:
        Tuple of (language_code, confidence).

    Example:
        >>> lang, conf = detect_language_with_confidence("Hello world")
        >>> print(f"{lang} ({conf:.2%})")
        en (99.99%)
    """
    if not text or not text.strip():
        return (fallback, 0.0)

    try:
        from langdetect import detect_langs

        # Get detection results with probabilities
        results = detect_langs(text)

        if not results:
            return (fallback, 0.0)

        # Get top result
        top_result = results[0]
        detected_lang = top_result.lang.lower()
        confidence = top_result.prob

        # Normalize language code
        detected_lang = normalize_language_code(detected_lang)

        # Check confidence threshold
        if confidence < min_confidence:
            logger.warning(
                f"Language detection confidence too low ({confidence:.2%}). "
                f"Using fallback: {fallback}"
            )
            return (fallback, confidence)

        # Validate supported
        if detected_lang not in SUPPORTED_LANGUAGES:
            logger.warning(
                f"Detected language '{detected_lang}' not supported. "
                f"Using fallback: {fallback}"
            )
            return (fallback, confidence)

        return (detected_lang, confidence)

    except ImportError:
        logger.warning("langdetect not installed")
        return (fallback, 0.0)
    except Exception as e:
        logger.error(f"Error in language detection: {e}")
        return (fallback, 0.0)


def normalize_language_code(code: str) -> str:
    """
    Normalize language code to ISO 639-1 format.

    Maps common variants to standard codes.

    Args:
        code: Language code to normalize.

    Returns:
        Normalized language code.

    Example:
        >>> normalize_language_code("zh-CN")
        'zh-cn'
        >>> normalize_language_code("ZH")
        'zh-cn'
    """
    code = code.lower().strip()

    # Map common variants
    mapping = {
        "zh": "zh-cn",  # Chinese -> Simplified Chinese
        "zh-tw": "zh-cn",  # Traditional -> Simplified (for consistency)
        "pt-br": "pt",  # Brazilian Portuguese -> Portuguese
        "es-mx": "es",  # Mexican Spanish -> Spanish
    }

    return mapping.get(code, code)


def is_language_supported(language_code: str) -> bool:
    """
    Check if a language is supported.

    Args:
        language_code: Language code to check (ISO 639-1).

    Returns:
        True if supported, False otherwise.

    Example:
        >>> is_language_supported("en")
        True
        >>> is_language_supported("xyz")
        False
    """
    normalized = normalize_language_code(language_code)
    return normalized in SUPPORTED_LANGUAGES


def get_language_name(language_code: str) -> Optional[str]:
    """
    Get the human-readable name of a language.

    Args:
        language_code: Language code (ISO 639-1).

    Returns:
        Language name or None if not found.

    Example:
        >>> get_language_name("en")
        'English'
        >>> get_language_name("es")
        'Spanish'
    """
    normalized = normalize_language_code(language_code)
    return SUPPORTED_LANGUAGES.get(normalized)


def detect_language_from_multiple_samples(
    texts: list[str],
    fallback: str = DEFAULT_LANGUAGE,
) -> str:
    """
    Detect language from multiple text samples (e.g., first few chunks).

    Uses majority voting for robustness.

    Args:
        texts: List of text samples to analyze.
        fallback: Fallback language if detection fails.

    Returns:
        Most common detected language.

    Example:
        >>> texts = ["Hello world", "Goodbye world", "Good morning"]
        >>> detect_language_from_multiple_samples(texts)
        'en'
    """
    if not texts:
        return fallback

    # Detect language for each sample
    detections: dict[str, int] = {}

    for text in texts:
        if not text or not text.strip():
            continue

        lang = detect_language(text, fallback=fallback)
        detections[lang] = detections.get(lang, 0) + 1

    if not detections:
        return fallback

    # Return most common
    most_common = max(detections.items(), key=lambda x: x[1])
    return most_common[0]
