"""Ollama (local) translation provider."""

import asyncio
import logging

import aiohttp

from languagebridge.config import LLMConfig
from languagebridge.llm.base import TranslationContext, TranslationProvider
from languagebridge.prompt import build_system_prompt

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "llama3"
MAX_RETRIES = 3
TIMEOUT_SECONDS = 10


class OllamaProvider(TranslationProvider):
    def __init__(self, config: LLMConfig) -> None:
        self._base_url = config.ollama_url.rstrip("/")
        self._model = config.model or DEFAULT_MODEL

    @property
    def display_name(self) -> str:
        return f"Ollama ({self._model})"

    async def translate(self, text: str, context: TranslationContext) -> str:
        system_prompt = build_system_prompt(context)
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "stream": False,
            "options": {"temperature": 0.3},
        }

        for attempt in range(MAX_RETRIES):
            try:
                timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return data["message"]["content"].strip()
                        body = await resp.text()
                        logger.warning(
                            "Ollama API error (attempt %d/%d): %d %s",
                            attempt + 1,
                            MAX_RETRIES,
                            resp.status,
                            body[:200],
                        )
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(
                    "Ollama request failed (attempt %d/%d): %s",
                    attempt + 1,
                    MAX_RETRIES,
                    e,
                )

            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2**attempt)

        logger.error("Ollama translation failed after %d attempts", MAX_RETRIES)
        return "[SKIP]"
