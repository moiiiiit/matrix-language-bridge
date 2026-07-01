"""Translation orchestrator — detection, LLM call, and Matrix reply."""

import logging
import re
import hashlib
from dataclasses import dataclass
from typing import Any

from mautrix.types import EventType, MessageType, RoomID, TextMessageEventContent

from languagebridge.config import Config
from languagebridge.detection import detect_language
from languagebridge.llm.base import TranslationContext, TranslationProvider
from languagebridge.preprocess import apply_preprocess
from languagebridge.storage import Storage

logger = logging.getLogger(__name__)


def _looks_like_charje_runes(text: str) -> bool:
    chars = [ch for ch in text if not ch.isspace()]
    if not chars:
        return False
    rune_count = sum(1 for ch in chars if 0x16A0 <= ord(ch) <= 0x16FF)
    return (rune_count / len(chars)) >= 0.6


_ROMANIZED_MARATHI_HINTS = {
    "kasa",
    "kashi",
    "kay",
    "kaay",
    "ahe",
    "aahe",
    "nahi",
    "nahiye",
    "mala",
    "tula",
    "mi",
    "tu",
    "ghari",
    "kam",
    "zhala",
    "aala",
    "ala",
}


def _looks_like_romanized_marathi(text: str) -> bool:
    tokens = re.findall(r"[a-zA-Z]+", text.lower())
    if len(tokens) < 3:
        return False
    hits = sum(1 for t in tokens if t in _ROMANIZED_MARATHI_HINTS)
    return hits >= 2


def _normalized_detected_language(profile, detected_language: str, text: str, confidence: float) -> str:
    """Improve source hint for bidirectional profiles when detector is uncertain."""
    if not profile.bidirectional_with:
        return detected_language
    if detected_language in {profile.target_language, profile.bidirectional_with}:
        return detected_language
    if confidence < 0.6 and _looks_like_romanized_marathi(text):
        return profile.bidirectional_with
    return detected_language


def _effective_target_language(profile, detected_language: str) -> str:
    if profile.bidirectional_with and detected_language == profile.target_language:
        return profile.bidirectional_with
    return profile.target_language


@dataclass
class MessageDecision:
    profile: Any
    text_for_translation: str
    preprocess_applied: bool
    detection: Any
    normalized_detected: str
    effective_target: str


def _translation_cache_key(
    profile_id: str,
    text_for_translation: str,
    source_language_hint: str,
    target_language: str,
    prompt_appendix: str,
) -> str:
    prompt_version = hashlib.sha256(prompt_appendix.encode("utf-8")).hexdigest()[:16]
    return "|".join(
        [
            profile_id,
            source_language_hint,
            target_language,
            prompt_version,
            text_for_translation.strip(),
        ]
    )


def _prepare_message(profile: Any, text: str) -> tuple[str, bool]:
    preprocessed_text, preprocess_applied = apply_preprocess(text, profile.preprocess)
    if preprocess_applied:
        logger.debug("Applied preprocess for profile=%s: %r -> %r", profile.id, text[:80], preprocessed_text[:80])
    return (preprocessed_text if preprocess_applied else text), preprocess_applied


def _decide_translation(profile: Any, original_text: str, text_for_translation: str, preprocess_applied: bool) -> MessageDecision:
    detection = detect_language(text_for_translation)
    normalized_detected = _normalized_detected_language(
        profile, detection.language_code, text_for_translation, detection.confidence
    )
    effective_target = _effective_target_language(profile, normalized_detected)
    logger.debug(
        (
            "Original message=%r | detected=%s confidence=%.2f | "
            "profile=%s bidirectional=%s from=%s to=%s"
        ),
        original_text[:160],
        detection.language_code,
        detection.confidence,
        profile.id,
        bool(profile.bidirectional_with),
        normalized_detected,
        effective_target,
    )
    logger.debug(
        "Selected profile '%s' for room target=%s detected=%s normalized=%s effective_target=%s",
        profile.id,
        profile.target_language,
        detection.language_code,
        normalized_detected,
        effective_target,
    )
    return MessageDecision(
        profile=profile,
        text_for_translation=text_for_translation,
        preprocess_applied=preprocess_applied,
        detection=detection,
        normalized_detected=normalized_detected,
        effective_target=effective_target,
    )


def _should_skip(profile: Any, original_text: str, decision: MessageDecision) -> bool:
    if profile.id == "charje_english_runes" and not decision.preprocess_applied and not _looks_like_charje_runes(
        original_text
    ):
        return True
    if (
        not decision.preprocess_applied
        and decision.detection.language_code == decision.effective_target
        and decision.detection.confidence > 0.7
    ):
        return True
    return False


async def _translate_with_retry(
    provider: TranslationProvider,
    text_for_translation: str,
    context: TranslationContext,
    profile: Any,
    normalized_detected: str,
) -> str | None:
    try:
        result = await provider.translate(text_for_translation, context)
    except Exception:
        logger.exception("Translation provider error")
        return None

    if result.strip() != "[SKIP]":
        return result

    logger.debug("Provider requested SKIP")
    should_retry = profile.bidirectional_with and normalized_detected in {
        profile.target_language,
        profile.bidirectional_with,
    }
    if not should_retry:
        return None

    retry_context = TranslationContext(
        family_name=context.family_name,
        source_language_hint=context.source_language_hint,
        target_language=context.target_language,
        preserve_terms=context.preserve_terms,
        dialect=context.dialect,
        tone=context.tone,
        prompt_appendix=(
            f"{context.prompt_appendix}\n"
            "For this message, do not output [SKIP]. Translate to the target language."
        ),
    )
    try:
        result = await provider.translate(text_for_translation, retry_context)
        logger.debug("Retry translation result: %s", result[:80])
    except Exception:
        logger.exception("Retry translation provider error")
        return None
    if result.strip() == "[SKIP]":
        return None
    return result


async def _translate_preprocess_only(
    provider: TranslationProvider, text_for_translation: str, context: TranslationContext
) -> str | None:
    non_skip_context = TranslationContext(
        family_name=context.family_name,
        source_language_hint=context.source_language_hint,
        target_language=context.target_language,
        preserve_terms=context.preserve_terms,
        dialect=context.dialect,
        tone=context.tone,
        prompt_appendix=(
            f"{context.prompt_appendix}\n"
            "IMPORTANT — Preprocessed input mode: the text below has already been "
            "converted from a non-Latin script into a phonetic/IPA representation. "
            "It is NOT already in the target language. "
            "Your job is to interpret the phonetics and output natural target-language text. "
            "You MUST NOT return [SKIP] under any circumstances in this mode."
        ),
    )
    try:
        result = await provider.translate(text_for_translation, non_skip_context)
    except Exception:
        logger.exception("Translation provider error (preprocess mode)")
        return None
    if result.strip() == "[SKIP]":
        # LLM still returned [SKIP] despite the instruction not to (e.g. it
        # misread IPA as already-English).  Return None so the caller treats
        # this as untranslatable and sends no reply — never surface the raw
        # preprocessed (IPA) text to the user.
        return None
    return result


async def handle_message(
    room_id: RoomID,
    event_id: str,
    sender: str,
    body: str,
    config: Config,
    provider: TranslationProvider,
    storage: Storage,
    send_reply,
) -> None:
    """Process a single message through the translation pipeline.

    send_reply is an async callable: send_reply(room_id, event_id, text) -> None
    """
    logger.debug("Handle message event_id=%s room=%s sender=%s", event_id, room_id, sender)

    # 1. Ignore own messages
    if sender == config.matrix.user_id:
        logger.debug("Skipping own message event_id=%s", event_id)
        return

    # 2. Dedup check
    if await storage.is_processed(event_id):
        logger.debug("Skipping duplicate event_id=%s", event_id)
        return

    # 3. Room filter
    if config.family.rooms != ["*"] and str(room_id) not in config.family.rooms:
        logger.debug("Skipping message outside configured rooms room=%s", room_id)
        return

    # 4. Skip empty or whitespace-only
    text = body.strip()
    if not text:
        logger.debug("Skipping empty/whitespace message event_id=%s", event_id)
        return

    profile = config.profile_for_room(str(room_id))
    text_for_translation, preprocess_applied = _prepare_message(profile, text)
    decision = _decide_translation(profile, text, text_for_translation, preprocess_applied)

    if _should_skip(profile, text, decision):
        logger.debug("Skipping message after decision checks event_id=%s", event_id)
        await storage.mark_processed(event_id, str(room_id))
        return

    # 8. Build translation context
    context = TranslationContext(
        family_name=config.family.name,
        source_language_hint=decision.normalized_detected,
        target_language=decision.effective_target,
        prompt_appendix=profile.prompt_appendix,
        preserve_terms=profile.preserve_terms or config.family.preserve_terms,
        dialect=profile.dialect or config.family.dialect,
    )

    cache_key = _translation_cache_key(
        profile.id,
        text_for_translation,
        context.source_language_hint,
        context.target_language,
        context.prompt_appendix,
    )
    cached = await storage.get_cached_translation(cache_key)
    if cached is not None:
        logger.info("Translation cache hit profile=%s room=%s", profile.id, room_id)
        result = cached
    else:
        logger.debug("Translation cache miss profile=%s room=%s", profile.id, room_id)
        # 9. Call LLM
        if decision.preprocess_applied:
            result = await _translate_preprocess_only(provider, text_for_translation, context)
        else:
            result = await _translate_with_retry(
                provider,
                text_for_translation,
                context,
                profile,
                decision.normalized_detected,
            )
        if result is None:
            await storage.mark_processed(event_id, str(room_id))
            return
        await storage.set_cached_translation(cache_key, result)

    # 10. Format reply
    reply_text = f"\U0001f310 {result}"

    # 11. Send reply
    try:
        await send_reply(room_id, event_id, reply_text)
        logger.info("Sent translation reply event_id=%s room=%s profile=%s", event_id, room_id, profile.id)
    except Exception:
        logger.exception("Failed to send translation reply")

    # 12. Mark as processed
    await storage.mark_processed(event_id, str(room_id))
