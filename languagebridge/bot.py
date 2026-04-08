"""Matrix event handler — wires mautrix events to the translation pipeline."""

import logging
from typing import Any

from mautrix.client import Client as MatrixClient
from mautrix.types import (
    EventType,
    MessageEvent,
    MessageType,
    ReactionEvent,
    RelationType,
    RoomID,
)

from languagebridge.config import Config
from languagebridge.message_content import text_content
from languagebridge.llm.base import TranslationProvider
from languagebridge.storage import Storage
from languagebridge.translation import handle_message

logger = logging.getLogger(__name__)


class LanguageBridgeBot:
    def __init__(
        self,
        client: MatrixClient,
        config: Config,
        provider: TranslationProvider,
        storage: Storage,
    ) -> None:
        self._client = client
        self._config = config
        self._provider = provider
        self._storage = storage
        self._warned_encrypted_rooms: set[str] = set()

    def register_handlers(self) -> None:
        """Register Matrix event handlers based on trigger_mode."""
        mode = self._config.family.trigger_mode
        # Without a crypto machine, m.room.encrypted never becomes plain text — warn once per room.
        if not self._client.crypto_enabled:
            self._client.add_event_handler(EventType.ROOM_ENCRYPTED, self._on_encrypted_message)

        if mode == "auto":
            self._client.add_event_handler(EventType.ROOM_MESSAGE, self._on_message)
        elif mode == "reaction":
            self._client.add_event_handler(EventType.REACTION, self._on_reaction)
        elif mode == "command":
            self._client.add_event_handler(EventType.ROOM_MESSAGE, self._on_command)

        logger.info("Registered handlers for trigger_mode=%s", mode)

    async def _on_encrypted_message(self, evt: Any) -> None:
        """Warn once per room that encrypted payloads are not translated."""
        room_id = str(getattr(evt, "room_id", "unknown"))
        if room_id in self._warned_encrypted_rooms:
            return
        self._warned_encrypted_rooms.add(room_id)
        logger.warning(
            "Encrypted event seen in room %s. LanguageBridge currently skips encrypted "
            "messages because Matrix E2EE decryption is not configured for this bot.",
            room_id,
        )

    async def _on_message(self, evt: MessageEvent) -> None:
        """Handle messages in auto mode — translate every foreign message."""
        if evt.content.msgtype != MessageType.TEXT:
            return
        body = evt.content.body
        if not body:
            return

        await handle_message(
            room_id=evt.room_id,
            event_id=str(evt.event_id),
            sender=str(evt.sender),
            body=body,
            config=self._config,
            provider=self._provider,
            storage=self._storage,
            send_reply=self._send_reply,
        )

    async def _on_reaction(self, evt: ReactionEvent) -> None:
        """Handle reactions in reaction mode — translate when trigger emoji is used."""
        relates_to = evt.content.relates_to
        if not relates_to or relates_to.key != self._config.family.reaction_trigger:
            return

        target_event_id = str(relates_to.event_id)

        # Fetch the original message
        try:
            original = await self._client.get_event(evt.room_id, relates_to.event_id)
        except Exception:
            logger.warning("Could not fetch event %s for reaction translation", target_event_id)
            return

        if not hasattr(original.content, "body") or not original.content.body:
            return

        await handle_message(
            room_id=evt.room_id,
            event_id=target_event_id,
            sender=str(original.sender),
            body=original.content.body,
            config=self._config,
            provider=self._provider,
            storage=self._storage,
            send_reply=self._send_reply,
        )

    async def _on_command(self, evt: MessageEvent) -> None:
        """Handle messages in command mode — translate when command prefix is used."""
        if evt.content.msgtype != MessageType.TEXT:
            return
        body = evt.content.body
        if not body:
            return

        prefix = self._config.family.command_prefix
        if not body.strip().startswith(prefix):
            return

        # If the command is a reply to another message, translate the replied-to message
        relates_to = evt.content.get("m.relates_to")
        if relates_to and relates_to.get("m.in_reply_to"):
            reply_event_id = relates_to["m.in_reply_to"]["event_id"]
            try:
                original = await self._client.get_event(evt.room_id, reply_event_id)
            except Exception:
                logger.warning("Could not fetch replied-to event %s", reply_event_id)
                return

            if hasattr(original.content, "body") and original.content.body:
                await handle_message(
                    room_id=evt.room_id,
                    event_id=str(reply_event_id),
                    sender=str(original.sender),
                    body=original.content.body,
                    config=self._config,
                    provider=self._provider,
                    storage=self._storage,
                    send_reply=self._send_reply,
                )
            return

        # Otherwise translate the text after the command prefix
        text_to_translate = body.strip()[len(prefix) :].strip()
        if text_to_translate:
            await handle_message(
                room_id=evt.room_id,
                event_id=str(evt.event_id),
                sender=str(evt.sender),
                body=text_to_translate,
                config=self._config,
                provider=self._provider,
                storage=self._storage,
                send_reply=self._send_reply,
            )

    async def _send_reply(self, room_id: RoomID, event_id: str, text: str) -> None:
        """Send a threaded reply (falls back to plain reply)."""
        content = text_content(text, MessageType.TEXT, self._config.ui)

        # Use threading (MSC3440 / stable threads)
        content["m.relates_to"] = {
            "rel_type": RelationType.THREAD.value,
            "event_id": event_id,
            "is_falling_back": True,
            "m.in_reply_to": {"event_id": event_id},
        }

        await self._client.send_message_event(
            room_id, EventType.ROOM_MESSAGE, content
        )

    async def send_startup_message(self) -> None:
        """Send a startup notification to configured rooms."""
        target_lang = self._config.default_profile.target_language
        provider_name = self._provider.display_name
        msg = (
            f"LanguageBridge connected \u2713 \u2014 watching for messages to translate "
            f"into {target_lang}. Powered by {provider_name}."
        )

        rooms = self._config.family.rooms
        if rooms == ["*"]:
            # Send to the first 5 joined rooms
            joined = await self._client.get_joined_rooms()
            rooms_to_notify = [str(r) for r in joined[:5]]
        else:
            rooms_to_notify = rooms

        for room_id in rooms_to_notify:
            try:
                content = text_content(msg, MessageType.NOTICE, self._config.ui)
                await self._client.send_message_event(
                    RoomID(room_id), EventType.ROOM_MESSAGE, content
                )
            except Exception:
                logger.warning("Failed to send startup message to %s", room_id)
