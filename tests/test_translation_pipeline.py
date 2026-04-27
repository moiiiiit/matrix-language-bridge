"""Async unit tests for handle_message: filters, profile routing, SKIP retry, replies."""

from unittest.mock import AsyncMock, patch

import pytest
from mautrix.types import RoomID

from languagebridge.config import (
    Config,
    FamilyConfig,
    LLMConfig,
    MatrixConfig,
    PreprocessConfig,
    TranslationProfile,
    UIConfig,
)
from languagebridge.detection import DetectionResult
from languagebridge.llm.base import TranslationContext, TranslationProvider
from languagebridge.translation import handle_message

ROOM = RoomID("!room:matrix.org")


def _config(
    *,
    rooms: list[str] | None = None,
    room_profiles: dict[str, str] | None = None,
    user_id: str = "@bot:matrix.org",
    profile_key: str = "p",
    profile: TranslationProfile | None = None,
) -> Config:
    prof = profile or TranslationProfile(
        id="p",
        target_language="en",
        reply_target_label="English",
        prompt_appendix="",
    )
    return Config(
        family=FamilyConfig(
            name="Fam",
            profile=profile_key,
            room_profiles=room_profiles or {},
            rooms=rooms if rooms is not None else ["*"],
        ),
        matrix=MatrixConfig(
            homeserver_url="https://matrix.org",
            access_token="t",
            user_id=user_id,
        ),
        llm=LLMConfig(provider="anthropic", api_key="k"),
        ui=UIConfig(),
        profiles={profile_key: prof},
    )


class MemoryStorage:
    def __init__(self) -> None:
        self.processed: set[str] = set()
        self.mark_calls: list[tuple[str, str]] = []
        self.translation_cache: dict[str, str] = {}

    async def is_processed(self, event_id: str) -> bool:
        return event_id in self.processed

    async def mark_processed(self, event_id: str, room_str: str) -> None:
        self.processed.add(event_id)
        self.mark_calls.append((event_id, room_str))

    async def get_cached_translation(self, cache_key: str) -> str | None:
        return self.translation_cache.get(cache_key)

    async def set_cached_translation(self, cache_key: str, translated_text: str) -> None:
        self.translation_cache[cache_key] = translated_text


class ListProvider(TranslationProvider):
    def __init__(self, results: list[str]) -> None:
        self._results = list(results)
        self.calls: list[tuple[str, TranslationContext]] = []

    async def translate(self, text: str, context: TranslationContext) -> str:
        self.calls.append((text, context))
        if not self._results:
            raise RuntimeError("no scripted translation results left")
        return self._results.pop(0)

    @property
    def display_name(self) -> str:
        return "list"


@pytest.fixture
def storage() -> MemoryStorage:
    return MemoryStorage()


@pytest.mark.asyncio
async def test_skips_own_message(storage: MemoryStorage) -> None:
    cfg = _config(user_id="@me:matrix.org")
    send = AsyncMock()
    prov = ListProvider(["unused"])
    with patch(
        "languagebridge.translation.detect_language",
        return_value=DetectionResult("en", 0.9),
    ):
        await handle_message(
            ROOM, "$1", "@me:matrix.org", "hello world test", cfg, prov, storage, send
        )
    assert not prov.calls
    send.assert_not_called()


@pytest.mark.asyncio
async def test_skips_duplicate_event(storage: MemoryStorage) -> None:
    cfg = _config()
    storage.processed.add("$dup")
    send = AsyncMock()
    prov = ListProvider(["unused"])
    with patch(
        "languagebridge.translation.detect_language",
        return_value=DetectionResult("en", 0.9),
    ):
        await handle_message(
            ROOM, "$dup", "@user:matrix.org", "hello world test", cfg, prov, storage, send
        )
    assert not prov.calls


@pytest.mark.asyncio
async def test_skips_outside_configured_rooms(storage: MemoryStorage) -> None:
    limited = _config(rooms=["!other:matrix.org"])
    send = AsyncMock()
    prov = ListProvider(["unused"])
    with patch(
        "languagebridge.translation.detect_language",
        return_value=DetectionResult("en", 0.9),
    ):
        await handle_message(
            ROOM, "$1", "@u:matrix.org", "hello world test", limited, prov, storage, send
        )
    assert not prov.calls


@pytest.mark.asyncio
async def test_skips_whitespace_only(storage: MemoryStorage) -> None:
    cfg = _config()
    send = AsyncMock()
    prov = ListProvider(["unused"])
    with patch(
        "languagebridge.translation.detect_language",
        return_value=DetectionResult("en", 0.9),
    ):
        await handle_message(ROOM, "$1", "@u:matrix.org", "   \n", cfg, prov, storage, send)
    assert not prov.calls


@pytest.mark.asyncio
async def test_skips_short_ascii_without_non_ascii(storage: MemoryStorage) -> None:
    cfg = _config()
    send = AsyncMock()
    prov = ListProvider(["unused"])
    with patch(
        "languagebridge.translation.detect_language",
        return_value=DetectionResult("en", 0.9),
    ):
        await handle_message(ROOM, "$1", "@u:matrix.org", "a b", cfg, prov, storage, send)
    assert not prov.calls
    assert ("$1", str(ROOM)) in storage.mark_calls


@pytest.mark.asyncio
async def test_one_way_skips_high_confidence_same_as_target(storage: MemoryStorage) -> None:
    cfg = _config()
    send = AsyncMock()
    prov = ListProvider(["unused"])
    with patch(
        "languagebridge.translation.detect_language",
        return_value=DetectionResult("en", 0.9),
    ):
        await handle_message(
            ROOM, "$1", "@u:matrix.org", "hello there world", cfg, prov, storage, send
        )
    assert not prov.calls
    send.assert_not_called()
    assert ("$1", str(ROOM)) in storage.mark_calls


@pytest.mark.asyncio
async def test_translates_builds_context_and_sends_reply(storage: MemoryStorage) -> None:
    cfg = _config(
        profile=TranslationProfile(
            id="p",
            target_language="en",
            reply_target_label="English",
            prompt_appendix="APPX",
        )
    )
    send = AsyncMock()
    prov = ListProvider(["Bonjour"])
    with patch(
        "languagebridge.translation.detect_language",
        return_value=DetectionResult("fr", 0.9),
    ):
        await handle_message(
            ROOM, "$1", "@u:matrix.org", "hello world here", cfg, prov, storage, send
        )
    assert len(prov.calls) == 1
    _, ctx = prov.calls[0]
    assert ctx.source_language_hint == "fr"
    assert ctx.target_language == "en"
    assert ctx.prompt_appendix == "APPX"
    send.assert_awaited_once()
    _rid, _eid, reply_text = send.await_args[0]
    assert _rid == ROOM
    assert _eid == "$1"
    assert "fr" in reply_text
    assert "English" in reply_text
    assert "Bonjour" in reply_text
    assert ("$1", str(ROOM)) in storage.mark_calls


@pytest.mark.asyncio
async def test_bidirectional_reply_label_uses_effective_target(storage: MemoryStorage) -> None:
    cfg = _config(
        profile=TranslationProfile(
            id="marathi",
            target_language="en",
            reply_target_label="English",
            bidirectional_with="mr",
            prompt_appendix="M",
        )
    )
    send = AsyncMock()
    prov = ListProvider(["नमस्कार"])
    with patch(
        "languagebridge.translation.detect_language",
        return_value=DetectionResult("en", 0.9),
    ):
        await handle_message(
            ROOM, "$1", "@u:matrix.org", "hello world here", cfg, prov, storage, send
        )
    reply = send.await_args[0][2]
    assert "[en → mr]" in reply
    assert "नमस्कार" in reply


@pytest.mark.asyncio
async def test_bidirectional_skip_retries_with_no_skip_appendix(storage: MemoryStorage) -> None:
    cfg = _config(
        profile=TranslationProfile(
            id="marathi",
            target_language="en",
            bidirectional_with="mr",
            reply_target_label="English",
            prompt_appendix="BASE",
        )
    )
    send = AsyncMock()
    prov = ListProvider(["[SKIP]", "झालं"])
    with patch(
        "languagebridge.translation.detect_language",
        return_value=DetectionResult("en", 0.85),
    ):
        await handle_message(
            ROOM, "$1", "@u:matrix.org", "hello world here", cfg, prov, storage, send
        )
    assert len(prov.calls) == 2
    assert "BASE" in prov.calls[1][1].prompt_appendix
    assert "do not output [SKIP]" in prov.calls[1][1].prompt_appendix
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_skip_no_retry_when_not_bidirectional(storage: MemoryStorage) -> None:
    cfg = _config()
    prov = ListProvider(["[SKIP]"])
    send = AsyncMock()
    with patch(
        "languagebridge.translation.detect_language",
        return_value=DetectionResult("fr", 0.9),
    ):
        await handle_message(
            ROOM, "$1", "@u:matrix.org", "hello world here", cfg, prov, storage, send
        )
    assert len(prov.calls) == 1
    send.assert_not_called()
    assert "$1" in storage.processed


@pytest.mark.asyncio
async def test_skip_retry_second_skip_marks_processed_no_send(storage: MemoryStorage) -> None:
    cfg = _config(
        profile=TranslationProfile(
            id="marathi",
            target_language="en",
            bidirectional_with="mr",
            reply_target_label="English",
        )
    )
    prov = ListProvider(["[SKIP]", "[SKIP]"])
    send = AsyncMock()
    with patch(
        "languagebridge.translation.detect_language",
        return_value=DetectionResult("en", 0.85),
    ):
        await handle_message(
            ROOM, "$1", "@u:matrix.org", "hello world here", cfg, prov, storage, send
        )
    assert len(prov.calls) == 2
    send.assert_not_called()
    assert "$1" in storage.processed


@pytest.mark.asyncio
async def test_provider_error_marks_processed_without_send(storage: MemoryStorage) -> None:
    class Boom(TranslationProvider):
        async def translate(self, text: str, context: TranslationContext) -> str:
            raise RuntimeError("boom")

        @property
        def display_name(self) -> str:
            return "boom"

    cfg = _config()
    send = AsyncMock()
    with patch(
        "languagebridge.translation.detect_language",
        return_value=DetectionResult("fr", 0.9),
    ):
        await handle_message(
            ROOM, "$1", "@u:matrix.org", "hello world here", cfg, Boom(), storage, send
        )
    send.assert_not_called()
    assert "$1" in storage.processed


@pytest.mark.asyncio
async def test_profile_for_room_uses_room_overrides(storage: MemoryStorage) -> None:
    cfg = Config(
        family=FamilyConfig(
            name="Fam",
            profile="default",
            room_profiles={str(ROOM): "fr"},
            rooms=["*"],
        ),
        matrix=MatrixConfig(
            homeserver_url="https://matrix.org",
            access_token="t",
            user_id="@bot:matrix.org",
        ),
        llm=LLMConfig(provider="anthropic", api_key="k"),
        ui=UIConfig(),
        profiles={
            "default": TranslationProfile(
                id="default", target_language="en", reply_target_label="en"
            ),
            "fr": TranslationProfile(
                id="fr",
                target_language="fr",
                reply_target_label="fr",
                prompt_appendix="FR_ONLY",
            ),
        },
    )
    prov = ListProvider(["bonjour monde"])
    send = AsyncMock()
    with patch(
        "languagebridge.translation.detect_language",
        return_value=DetectionResult("en", 0.9),
    ):
        await handle_message(
            ROOM, "$1", "@u:matrix.org", "hello world here", cfg, prov, storage, send
        )
    assert prov.calls[0][1].prompt_appendix == "FR_ONLY"
    assert prov.calls[0][1].target_language == "fr"


@pytest.mark.asyncio
async def test_romanized_marathi_low_confidence_sets_context_hints(storage: MemoryStorage) -> None:
    cfg = _config(
        profile=TranslationProfile(
            id="marathi",
            target_language="en",
            reply_target_label="English",
            bidirectional_with="mr",
        )
    )
    prov = ListProvider(["done"])
    send = AsyncMock()
    text = "kasa chalu ahe kam ala ka ghari"
    with patch(
        "languagebridge.translation.detect_language",
        return_value=DetectionResult("id", 0.34),
    ):
        await handle_message(ROOM, "$1", "@u:matrix.org", text, cfg, prov, storage, send)
    ctx = prov.calls[0][1]
    assert ctx.source_language_hint == "mr"
    assert ctx.target_language == "en"
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_charje_skips_non_rune_input(storage: MemoryStorage) -> None:
    cfg = _config(
        profile=TranslationProfile(
            id="charje_english_runes",
            target_language="en",
            reply_target_label="en",
            prompt_appendix="CHARJE",
        )
    )
    prov = ListProvider(["unused"])
    send = AsyncMock()
    with patch(
        "languagebridge.translation.detect_language",
        return_value=DetectionResult("en", 0.9),
    ):
        await handle_message(
            ROOM, "$1", "@u:matrix.org", "hello world here", cfg, prov, storage, send
        )
    assert len(prov.calls) == 0
    send.assert_not_called()


@pytest.mark.asyncio
async def test_charje_decodes_rune_input_to_english(storage: MemoryStorage) -> None:
    cfg = _config(
        profile=TranslationProfile(
            id="charje_english_runes",
            target_language="en",
            reply_target_label="en",
            prompt_appendix="CHARJE",
            preprocess=PreprocessConfig(
                kind="runes_to_phonetic",
                twin_map="languagebridge/profiles/charje_maps/twin.json",
                lone_map="languagebridge/profiles/charje_maps/lone.json",
            ),
        )
    )
    prov = ListProvider(["hello"])
    send = AsyncMock()
    with patch(
        "languagebridge.translation.detect_language",
        return_value=DetectionResult("unknown", 0.0),
    ):
        await handle_message(
            ROOM, "$1", "@u:matrix.org", "ᚻᛖᛚᛟ", cfg, prov, storage, send
        )
    assert len(prov.calls) == 1
    assert prov.calls[0][0] != "ᚻᛖᛚᛟ"
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_uses_cached_translation_on_repeat_text(storage: MemoryStorage) -> None:
    cfg = _config(
        profile=TranslationProfile(
            id="p",
            target_language="en",
            reply_target_label="English",
            prompt_appendix="APPX",
        )
    )
    send = AsyncMock()
    prov = ListProvider(["Bonjour", "unused"])
    with patch(
        "languagebridge.translation.detect_language",
        return_value=DetectionResult("fr", 0.9),
    ):
        await handle_message(
            ROOM, "$1", "@u:matrix.org", "hello world here", cfg, prov, storage, send
        )
        await handle_message(
            ROOM, "$2", "@u:matrix.org", "hello world here", cfg, prov, storage, send
        )
    # Second call should hit cache and avoid provider.
    assert len(prov.calls) == 1
    assert send.await_count == 2
