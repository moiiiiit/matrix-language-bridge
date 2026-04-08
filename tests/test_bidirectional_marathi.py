from languagebridge.translation import (
    _effective_target_language,
    _looks_like_romanized_marathi,
    _normalized_detected_language,
)


class _Profile:
    def __init__(self, target_language: str, bidirectional_with: str | None) -> None:
        self.target_language = target_language
        self.bidirectional_with = bidirectional_with


def test_romanized_marathi_heuristic_detects_common_text() -> None:
    assert _looks_like_romanized_marathi("kasa chalu ahe kam ala ka ghari")
    assert not _looks_like_romanized_marathi("hello how are you")


def test_bidirectional_normalizes_uncertain_detection_to_marathi() -> None:
    p = _Profile(target_language="en", bidirectional_with="mr")
    normalized = _normalized_detected_language(
        p, detected_language="id", text="kasa chalu ahe kam. ala ka ghari?", confidence=0.34
    )
    assert normalized == "mr"
    assert _effective_target_language(p, normalized) == "en"


def test_bidirectional_keeps_known_source_and_switches_target() -> None:
    p = _Profile(target_language="en", bidirectional_with="mr")
    assert _effective_target_language(p, "en") == "mr"
    assert _effective_target_language(p, "mr") == "en"


def test_normalization_does_not_override_high_confidence_wrong_guess() -> None:
    """Romanized-looking text with confident non-mr detection should stay as detected."""
    p = _Profile(target_language="en", bidirectional_with="mr")
    normalized = _normalized_detected_language(
        p,
        detected_language="id",
        text="kasa chalu ahe kam ala ka ghari",
        confidence=0.85,
    )
    assert normalized == "id"


def test_normalization_keeps_en_or_mr_when_detector_matches() -> None:
    p = _Profile(target_language="en", bidirectional_with="mr")
    assert _normalized_detected_language(p, "en", "x", 0.9) == "en"
    assert _normalized_detected_language(p, "mr", "x", 0.9) == "mr"


def test_one_way_profile_passes_through_detector_code() -> None:
    p = _Profile(target_language="en", bidirectional_with=None)
    assert _normalized_detected_language(p, "id", "kasa ahe", 0.2) == "id"
