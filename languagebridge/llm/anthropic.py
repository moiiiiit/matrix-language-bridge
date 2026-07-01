"""Anthropic (Claude) translation provider."""

import asyncio
import json
import logging

import aiohttp

from languagebridge.config import LLMConfig
from languagebridge.llm.base import TranslationContext, TranslationProvider
from languagebridge.prompt import build_system_prompt

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
API_URL = "https://api.anthropic.com/v1/messages"
MAX_RETRIES = 3
TIMEOUT_SECONDS = 30


class AnthropicProvider(TranslationProvider):
    def __init__(self, config: LLMConfig) -> None:
        if not config.api_key:
            raise ValueError("Anthropic provider requires an api_key")
        self._api_key = config.api_key
        self._model = config.model or DEFAULT_MODEL

    @property
    def display_name(self) -> str:
        return f"Anthropic ({self._model})"

    async def translate(self, text: str, context: TranslationContext) -> str:
        system_prompt = build_system_prompt(context)
        payload = {
            "model": self._model,
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": [{"role": "user", "content": text}],
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        for attempt in range(MAX_RETRIES):
            try:
                timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        API_URL, json=payload, headers=headers
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return data["content"][0]["text"].strip()
                        body = await resp.text()
                        logger.warning(
                            "Anthropic API error (attempt %d/%d): %d %s",
                            attempt + 1,
                            MAX_RETRIES,
                            resp.status,
                            body[:200],
                        )
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(
                    "Anthropic request failed (attempt %d/%d): %s: %s",
                    attempt + 1,
                    MAX_RETRIES,
                    type(e).__name__,
                    e or "(no message)",
                )

            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2**attempt)

        logger.error("Anthropic translation failed after %d attempts", MAX_RETRIES)
        return "[SKIP]"
