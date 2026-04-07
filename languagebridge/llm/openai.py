"""OpenAI translation provider."""

import asyncio
import logging

import aiohttp

from languagebridge.config import LLMConfig
from languagebridge.llm.base import TranslationContext, TranslationProvider
from languagebridge.prompt import build_system_prompt

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"
API_URL = "https://api.openai.com/v1/chat/completions"
MAX_RETRIES = 3
TIMEOUT_SECONDS = 10


class OpenAIProvider(TranslationProvider):
    def __init__(self, config: LLMConfig) -> None:
        if not config.api_key:
            raise ValueError("OpenAI provider requires an api_key")
        self._api_key = config.api_key
        self._model = config.model or DEFAULT_MODEL

    @property
    def display_name(self) -> str:
        return f"OpenAI ({self._model})"

    async def translate(self, text: str, context: TranslationContext) -> str:
        system_prompt = build_system_prompt(context)
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "max_tokens": 1024,
            "temperature": 0.3,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
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
                            return data["choices"][0]["message"]["content"].strip()
                        body = await resp.text()
                        logger.warning(
                            "OpenAI API error (attempt %d/%d): %d %s",
                            attempt + 1,
                            MAX_RETRIES,
                            resp.status,
                            body[:200],
                        )
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(
                    "OpenAI request failed (attempt %d/%d): %s",
                    attempt + 1,
                    MAX_RETRIES,
                    e,
                )

            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2**attempt)

        logger.error("OpenAI translation failed after %d attempts", MAX_RETRIES)
        return "[SKIP]"
