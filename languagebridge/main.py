"""LanguageBridge entry point — load config, initialise components, start sync."""

import asyncio
import inspect
import logging
import os
import sys
from pathlib import Path

from mautrix.client import Client as MatrixClient

from languagebridge.bot import LanguageBridgeBot
from languagebridge.config import load_config
from languagebridge.llm import create_provider
from languagebridge.storage import Storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("languagebridge")


class SingleInstanceLock:
    """Prevent multiple bot processes from running concurrently."""

    def __init__(self, lock_path: str | Path) -> None:
        self._lock_path = Path(lock_path)
        self._fd: int | None = None

    def acquire(self) -> None:
        import fcntl

        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(self._lock_path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            logger.error(
                "Another LanguageBridge instance is already running "
                "(lock: %s).",
                self._lock_path,
            )
            raise SystemExit(1)

    def release(self) -> None:
        if self._fd is None:
            return
        import fcntl

        fcntl.flock(self._fd, fcntl.LOCK_UN)
        os.close(self._fd)
        self._fd = None


async def main() -> None:
    lock_path = os.environ.get("LOCK_PATH", "data/languagebridge.lock")
    process_lock = SingleInstanceLock(lock_path)
    process_lock.acquire()

    # 1. Load config
    config_path = os.environ.get("CONFIG_PATH", "config/config.yaml")
    logger.info("Loading config from %s", config_path)
    config = load_config(config_path)
    logger.info("Config loaded for family: %s", config.family.name)

    # 2. Initialise storage
    db_path = os.environ.get("DB_PATH", "data/languagebridge.db")
    storage = Storage(db_path)
    await storage.open()
    await storage.cleanup_old()
    logger.info("Storage initialised at %s", db_path)

    # 3. Initialise LLM provider
    provider = create_provider(config.llm)
    logger.info("LLM provider: %s", provider.display_name)

    # 4. Initialise Matrix client
    client = MatrixClient(
        base_url=config.matrix.homeserver_url,
        token=config.matrix.access_token,
        client_session=None,
    )
    client.parse_user_id(config.matrix.user_id)

    # Verify connection
    try:
        whoami = await client.whoami()
        logger.info("Connected to Matrix as %s", whoami.user_id)
    except Exception as e:
        logger.error("Failed to connect to Matrix homeserver: %s", e)
        await storage.close()
        sys.exit(1)

    # 5. Set up bot
    bot = LanguageBridgeBot(client, config, provider, storage)
    bot.register_handlers()

    # 6. Send startup message
    try:
        await bot.send_startup_message()
    except Exception:
        logger.warning("Failed to send startup messages (non-fatal)")

    # 7. Start sync loop
    logger.info(
        "Starting sync loop (trigger_mode=%s, target_language=%s)",
        config.family.trigger_mode,
        config.family.target_language,
    )
    try:
        await client.start(None)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        try:
            stop_result = client.stop()
            if inspect.isawaitable(stop_result):
                await stop_result
            await storage.close()
            logger.info("LanguageBridge stopped.")
        finally:
            process_lock.release()


def run() -> None:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
