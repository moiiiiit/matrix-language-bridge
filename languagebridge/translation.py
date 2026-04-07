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
    # 1. Ignore own messages
    if sender == config.matrix.user_id:
        return

    # 2. Dedup check
    if await storage.is_processed(event_id):
        return

    # 3. Room filter
    if config.family.rooms != ["*"] and str(room_id) not in config.family.rooms:
        return

    # 4. Skip empty or whitespace-only
    text = body.strip()
    if not text:
        return

    # 5. Language detection
    detection = detect_language(text)
    logger.debug(
        "Detected language=%s confidence=%.2f for: %s",
        detection.language_code,
        detection.confidence,
        text[:80],
    )

    # 6. Skip if already in target language with high confidence
    if (
        detection.language_code == config.family.target_language
        and detection.confidence > 0.7
    ):
        await storage.mark_processed(event_id, str(room_id))
        return

    # 7. Skip very short text without non-ASCII characters
    word_count = len(text.split())
    if word_count < 3 and not _has_non_ascii(text):
        await storage.mark_processed(event_id, str(room_id))
        return

    # 8. Build translation context
    context = TranslationContext(
        family_name=config.family.name,
        source_language_hint=detection.language_code,
        target_language=config.family.target_language,
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
        await storage.mark_processed(event_id, str(room_id))
        return

    # 10. Format reply
    source_lang = detection.language_code if detection.language_code != "unknown" else "?"
    reply_text = f"\U0001f310 [{source_lang} \u2192 {config.family.target_language}] {result}"

    # 11. Send reply
    try:
        await send_reply(room_id, event_id, reply_text)
    except Exception:
        logger.exception("Failed to send translation reply")

    # 12. Mark as processed
    await storage.mark_processed(event_id, str(room_id))
