"""Translation orchestrator — detection, LLM call, and Matrix reply."""

import logging
import re

from mautrix.types import EventType, MessageType, RoomID, TextMessageEventContent

from languagebridge.config import Config
from languagebridge.detection import detect_language
from languagebridge.llm.base import TranslationContext, TranslationProvider
from languagebridge.storage import Storage

logger = logging.getLogger(__name__)


def _has_non_ascii(text: str) -> bool:
    return bool(re.search(r"[^\x00-\x7F]", text))


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

    # 5. Language detection
    detection = detect_language(text)
    profile = config.profile_for_room(str(room_id))
    normalized_detected = _normalized_detected_language(
        profile, detection.language_code, text, detection.confidence
    )
    effective_target = _effective_target_language(profile, normalized_detected)
    translation_from = normalized_detected
    translation_to = effective_target
    logger.debug(
        (
            "Original message=%r | detected=%s confidence=%.2f | "
            "profile=%s bidirectional=%s from=%s to=%s"
        ),
        text[:160],
        detection.language_code,
        detection.confidence,
        profile.id,
        bool(profile.bidirectional_with),
        translation_from,
        translation_to,
    )
    logger.debug(
        "Selected profile '%s' for room=%s target=%s detected=%s normalized=%s effective_target=%s",
        profile.id,
        room_id,
        profile.target_language,
        detection.language_code,
        normalized_detected,
        effective_target,
    )

    # Charje room is decode-only: translate runes to English.
    if profile.id == "charje_english_runes" and not _looks_like_charje_runes(text):
        logger.debug("Skipping non-rune input for charje profile event_id=%s", event_id)
        await storage.mark_processed(event_id, str(room_id))
        return

    # 6. Skip if already in target language with high confidence
    if (
        detection.language_code == effective_target
        and detection.confidence > 0.7
    ):
        logger.debug("Skipping already-target-language event_id=%s", event_id)
        await storage.mark_processed(event_id, str(room_id))
        return

    # 7. Skip very short text without non-ASCII characters
    word_count = len(text.split())
    if word_count < 3 and not _has_non_ascii(text):
        logger.debug("Skipping short low-signal text event_id=%s", event_id)
        await storage.mark_processed(event_id, str(room_id))
        return

    # 8. Build translation context
    context = TranslationContext(
        family_name=config.family.name,
        source_language_hint=normalized_detected,
        target_language=effective_target,
        prompt_appendix=profile.prompt_appendix,
        preserve_terms=config.family.preserve_terms,
        dialect=config.family.dialect,
    )

    # 9. Call LLM
    try:
        result = await provider.translate(text, context)
    except Exception:
        logger.exception("Translation provider error")
        await storage.mark_processed(event_id, str(room_id))
        return

    if result.strip() == "[SKIP]":
        logger.debug("Provider requested SKIP for event_id=%s", event_id)
        # For bidirectional profiles, force one retry with explicit no-SKIP instruction.
        should_retry = profile.bidirectional_with and normalized_detected in {
            profile.target_language,
            profile.bidirectional_with,
        }
        if should_retry:
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
                result = await provider.translate(text, retry_context)
                logger.debug("Retry translation result for event_id=%s: %s", event_id, result[:80])
            except Exception:
                logger.exception("Retry translation provider error")
                await storage.mark_processed(event_id, str(room_id))
                return
            if result.strip() == "[SKIP]":
                await storage.mark_processed(event_id, str(room_id))
                return
        else:
            await storage.mark_processed(event_id, str(room_id))
            return

    # 10. Format reply
    source_lang = detection.language_code if detection.language_code != "unknown" else "?"
    tgt_label = effective_target if profile.bidirectional_with else profile.reply_target_label
    reply_text = f"\U0001f310 [{source_lang} \u2192 {tgt_label}] {result}"

    # 11. Send reply
    try:
        await send_reply(room_id, event_id, reply_text)
        logger.info("Sent translation reply event_id=%s room=%s profile=%s", event_id, room_id, profile.id)
    except Exception:
        logger.exception("Failed to send translation reply")

    # 12. Mark as processed
    await storage.mark_processed(event_id, str(room_id))
