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
from languagebridge.matrix_e2ee import attach_olm_machine, create_e2ee_stack
from languagebridge.storage import Storage

_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL, logging.INFO),
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
            os.close(self._fd)
            self._fd = None
            other_pid = _read_lock_pid(self._lock_path)
            hint = ""
            if other_pid is not None and _pid_is_alive(other_pid):
                hint = f" (lock file lists PID {other_pid} — stop that process, or: kill {other_pid})"
            elif other_pid is not None:
                hint = (
                    f" (stale PID {other_pid} in lock file; no process is using it — "
                    f"try: rm {self._lock_path})"
                )
            logger.error(
                "Another LanguageBridge instance is already running (lock: %s).%s",
                self._lock_path,
                hint,
            )
            raise SystemExit(1)
        try:
            os.ftruncate(self._fd, 0)
            os.write(self._fd, str(os.getpid()).encode())
        except OSError:
            pass

    def release(self) -> None:
        if self._fd is None:
            return
        import fcntl

        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None


def _read_lock_pid(path: Path) -> int | None:
    try:
        raw = path.read_text().strip()
        return int(raw) if raw.isdigit() else None
    except OSError:
        return None


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


async def main() -> None:
    lock_path = os.environ.get("LOCK_PATH", "data/languagebridge.lock")
    process_lock = SingleInstanceLock(lock_path)
    process_lock.acquire()
    logger.debug("Acquired single-instance lock at %s", lock_path)

    client: MatrixClient | None = None
    storage: Storage | None = None
    e2ee_stack = None

    try:
        # 1. Load config
        config_path = os.environ.get("CONFIG_PATH", "config/config.yaml")
        logger.info("Loading config from %s", config_path)
        config = load_config(config_path)
        logger.info("Config loaded for family: %s", config.family.name)
        logger.debug(
            "Profiles loaded: default=%s, room_overrides=%s",
            config.family.profile,
            len(config.family.room_profiles),
        )

        # 2. Initialise storage
        db_path = os.environ.get("DB_PATH", "data/languagebridge.db")
        storage = Storage(db_path)
        await storage.open()
        await storage.cleanup_old()
        logger.info("Storage initialised at %s", db_path)

        # 3. Initialise LLM provider
        provider = create_provider(config.llm)
        logger.info("LLM provider: %s", provider.display_name)
        logger.debug("Configured trigger_mode=%s rooms=%s", config.family.trigger_mode, config.family.rooms)

        # 4. Initialise Matrix client (optionally with E2EE stores)
        if config.matrix.encryption.enabled:
            try:
                e2ee_stack = await create_e2ee_stack(config)
            except RuntimeError as e:
                logger.error("%s", e)
                sys.exit(1)
        client = MatrixClient(
            base_url=config.matrix.homeserver_url,
            token=(config.matrix.access_token or "").strip(),
            client_session=None,
            state_store=e2ee_stack.state_store if e2ee_stack else None,
            sync_store=e2ee_stack.crypto_store if e2ee_stack else None,
        )
        # parse_user_id() only validates/splits; setting mxid ensures crypto upload payloads include user_id.
        client.mxid = config.matrix.user_id

        # Verify connection, with optional password login fallback.
        matrix_password = os.environ.get("LB_MATRIX_PASSWORD", "").strip() or (
            (config.matrix.password or "").strip()
        )
        try:
            whoami = await client.whoami()
            logger.info("Connected to Matrix as %s", whoami.user_id)
        except Exception as e:
            if not matrix_password:
                logger.error("Failed to connect to Matrix homeserver: %s", e)
                logger.error(
                    "Provide a valid matrix.access_token or set matrix.password / LB_MATRIX_PASSWORD."
                )
                sys.exit(1)
            logger.warning("Matrix token check failed (%s). Trying password login.", e)
            try:
                login_kwargs: dict[str, str] = {"password": matrix_password}
                # Reuse previous device ID from crypto store if present, so E2EE keys remain valid.
                if e2ee_stack is not None:
                    stored_device_id = await e2ee_stack.crypto_store.get_device_id()
                    if stored_device_id:
                        login_kwargs["device_id"] = str(stored_device_id)
                await client.login(**login_kwargs)
                whoami = await client.whoami()
                logger.info("Connected to Matrix via password login as %s", whoami.user_id)
            except Exception as login_error:
                logger.error("Matrix password login failed: %s", login_error)
                sys.exit(1)

        if e2ee_stack is not None:
            try:
                await attach_olm_machine(client, config, e2ee_stack, whoami)
            except Exception as e:
                logger.error("Failed to initialise Matrix E2EE: %s", e)
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
            "Starting sync loop (trigger_mode=%s, target_language=%s, e2ee=%s)",
            config.family.trigger_mode,
            config.default_profile.target_language,
            config.matrix.encryption.enabled,
        )
        try:
            await client.start(None)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
    finally:
        if e2ee_stack is not None:
            await e2ee_stack.database.stop()
        if client is not None:
            stop_result = client.stop()
            if inspect.isawaitable(stop_result):
                await stop_result
            # mautrix client.stop() may not fully close aiohttp session on some paths.
            await client.api.session.close()
        if storage is not None:
            await storage.close()
        process_lock.release()
        logger.info("LanguageBridge stopped.")


def run() -> None:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
