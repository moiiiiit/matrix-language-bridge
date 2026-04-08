"""Matrix end-to-end encryption (Megolm + Olm via mautrix)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from mautrix.client import Client as MatrixClient
from mautrix.client.state_store.memory import MemoryStateStore
from mautrix.types import Membership, RoomID, UserID, WhoamiResponse
from mautrix.util.async_db import Database

# NOTE: Do not import mautrix.crypto at module level — it requires python-olm (optional extra).
from yarl import URL

from languagebridge.config import Config, MatrixEncryptionConfig

logger = logging.getLogger(__name__)


class LanguageBridgeStateStore(MemoryStateStore):
    """In-memory room state plus :meth:`find_shared_rooms` required by :class:`OlmMachine`."""

    async def find_shared_rooms(self, user_id: UserID) -> list[RoomID]:
        shared: list[RoomID] = []
        for room_id, members in self.members.items():
            enc = await self.is_encrypted(room_id)
            if not enc:
                continue
            member = members.get(user_id)
            if member is not None and member.membership == Membership.JOIN:
                shared.append(room_id)
        return shared


@dataclass
class E2EEStack:
    state_store: LanguageBridgeStateStore
    crypto_store: object  # PgCryptoStore
    database: Database


def _resolve_pickle_key(enc: MatrixEncryptionConfig) -> str:
    if enc.pickle_key.strip():
        return enc.pickle_key.strip()
    env = os.environ.get("LB_MATRIX_PICKLE_KEY", "").strip()
    if env:
        return env
    return ""


def encryption_store_url(cfg: MatrixEncryptionConfig) -> str:
    """SQLite URL for mautrix :class:`~mautrix.util.async_db.Database`."""
    raw = (cfg.store_path or "data/languagebridge-e2ee.db").strip()
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(URL.build(scheme="sqlite", path=str(path.resolve())))


async def create_e2ee_stack(config: Config) -> E2EEStack:
    """Open the crypto database and construct stores. Does not set ``client.crypto`` yet."""
    try:
        import olm  # noqa: F401
        from mautrix.crypto import PgCryptoStore
    except ImportError as e:
        raise RuntimeError(
            "Matrix E2EE requires the python-olm package (and usually libolm on the system). "
            "Install with: poetry install --extras e2ee"
        ) from e
    if PgCryptoStore is None:
        raise RuntimeError(
            "Matrix E2EE requires asyncpg (mautrix only loads PgCryptoStore when it is installed). "
            "Install with: poetry install --extras e2ee"
        )

    enc = config.matrix.encryption
    pickle_key = _resolve_pickle_key(enc)
    if not pickle_key:
        raise RuntimeError(
            "matrix.encryption.enabled is true but no pickle_key is set. "
            "Set matrix.encryption.pickle_key in config or environment LB_MATRIX_PICKLE_KEY."
        )

    db_url = encryption_store_url(enc)
    crypto_db = Database.create(
        db_url,
        upgrade_table=PgCryptoStore.upgrade_table,
        db_args={"min_size": 1},
        log=logger.getChild("e2ee_db"),
    )
    await crypto_db.start()

    crypto_store = PgCryptoStore(config.matrix.user_id, pickle_key, crypto_db)
    state_store = LanguageBridgeStateStore()
    logger.info("Matrix E2EE crypto store ready at %s", db_url)
    return E2EEStack(state_store=state_store, crypto_store=crypto_store, database=crypto_db)


async def attach_olm_machine(
    client: MatrixClient,
    config: Config,
    stack: E2EEStack,
    whoami: WhoamiResponse,
) -> None:
    """Create :class:`OlmMachine`, assign ``client.crypto``, and sync device id into the store."""
    from mautrix.crypto import OlmMachine

    if whoami.device_id:
        client.device_id = whoami.device_id
    stored_id = await stack.crypto_store.get_device_id()
    if stored_id and whoami.device_id and str(stored_id) != str(whoami.device_id):
        logger.warning(
            "Crypto store device_id %s differs from /whoami device_id %s — keys may be invalid",
            stored_id,
            whoami.device_id,
        )
    if whoami.device_id:
        await stack.crypto_store.put_device_id(whoami.device_id)

    olm_machine = OlmMachine(client, stack.crypto_store, stack.state_store)
    await olm_machine.load()
    client.crypto = olm_machine

    logger.info(
        "Matrix E2EE active for %s (device=%s)",
        config.matrix.user_id,
        client.device_id or whoami.device_id,
    )
