"""Async SQLite storage for tracking processed message IDs."""

import time
from pathlib import Path

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_events (
    event_id TEXT PRIMARY KEY,
    room_id  TEXT NOT NULL,
    processed_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS translation_cache (
    cache_key TEXT PRIMARY KEY,
    translated_text TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0
);
"""


class Storage:
    def __init__(self, db_path: str | Path = "data/languagebridge.db"):
        self._db_path = str(db_path)
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def is_processed(self, event_id: str) -> bool:
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT 1 FROM processed_events WHERE event_id = ?", (event_id,)
        )
        return await cursor.fetchone() is not None

    async def mark_processed(self, event_id: str, room_id: str) -> None:
        assert self._db is not None
        await self._db.execute(
            "INSERT OR IGNORE INTO processed_events (event_id, room_id, processed_at) VALUES (?, ?, ?)",
            (event_id, room_id, int(time.time())),
        )
        await self._db.commit()

    async def cleanup_old(self, days: int = 30) -> None:
        assert self._db is not None
        cutoff = int(time.time()) - (days * 86400)
        await self._db.execute(
            "DELETE FROM processed_events WHERE processed_at < ?", (cutoff,)
        )
        await self._db.execute(
            "DELETE FROM translation_cache WHERE created_at < ?", (cutoff,)
        )
        await self._db.commit()

    async def get_cached_translation(self, cache_key: str) -> str | None:
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT translated_text FROM translation_cache WHERE cache_key = ?",
            (cache_key,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        await self._db.execute(
            "UPDATE translation_cache SET hit_count = hit_count + 1 WHERE cache_key = ?",
            (cache_key,),
        )
        await self._db.commit()
        return row[0]

    async def set_cached_translation(self, cache_key: str, translated_text: str) -> None:
        assert self._db is not None
        await self._db.execute(
            """
            INSERT INTO translation_cache (cache_key, translated_text, created_at, hit_count)
            VALUES (?, ?, ?, 0)
            ON CONFLICT(cache_key) DO UPDATE SET
                translated_text = excluded.translated_text,
                created_at = excluded.created_at
            """,
            (cache_key, translated_text, int(time.time())),
        )
        await self._db.commit()
