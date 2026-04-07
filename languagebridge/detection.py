"""Language detection using lingua-py."""

from dataclasses import dataclass

from lingua import Language, LanguageDetectorBuilder

SUPPORTED_LANGUAGES = [
    Language.ENGLISH,
    Language.HINDI,
    Language.MARATHI,
    Language.PUNJABI,
    Language.GUJARATI,
    Language.TAMIL,
    Language.TELUGU,
    Language.BENGALI,
    Language.SPANISH,
    Language.FRENCH,
    Language.GERMAN,
    Language.PORTUGUESE,
    Language.ITALIAN,
    Language.ARABIC,
    Language.CHINESE,
    Language.JAPANESE,
    Language.KOREAN,
    Language.RUSSIAN,
    Language.TURKISH,
    Language.DUTCH,
    Language.POLISH,
    Language.VIETNAMESE,
    Language.THAI,
    Language.INDONESIAN,
]

# Language code mapping (lingua Language enum -> ISO 639-1)
_LANG_CODES: dict[Language, str] = {
    Language.ENGLISH: "en",
    Language.HINDI: "hi",
    Language.MARATHI: "mr",
    Language.PUNJABI: "pa",
    Language.GUJARATI: "gu",
    Language.TAMIL: "ta",
    Language.TELUGU: "te",
    Language.BENGALI: "bn",
    Language.SPANISH: "es",
    Language.FRENCH: "fr",
    Language.GERMAN: "de",
    Language.PORTUGUESE: "pt",
    Language.ITALIAN: "it",
    Language.ARABIC: "ar",
    Language.CHINESE: "zh",
    Language.JAPANESE: "ja",
    Language.KOREAN: "ko",
    Language.RUSSIAN: "ru",
    Language.TURKISH: "tr",
    Language.DUTCH: "nl",
    Language.POLISH: "pl",
    Language.VIETNAMESE: "vi",
    Language.THAI: "th",
    Language.INDONESIAN: "id",
}


@dataclass
class DetectionResult:
    language_code: str
    confidence: float


_detector = (
    LanguageDetectorBuilder.from_languages(*SUPPORTED_LANGUAGES)
    .with_minimum_relative_distance(0.15)
    .build()
)


def detect_language(text: str) -> DetectionResult:
    """Detect the language of the given text.

    Returns a DetectionResult with language_code and confidence.
    For undetectable text, returns ("unknown", 0.0).
    """
    confidence_values = _detector.compute_language_confidence_values(text)
    if not confidence_values:
        return DetectionResult(language_code="unknown", confidence=0.0)

    top = confidence_values[0]
    lang_code = _LANG_CODES.get(top.language, "unknown")
    return DetectionResult(language_code=lang_code, confidence=top.value)
