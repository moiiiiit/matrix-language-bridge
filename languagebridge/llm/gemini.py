"""Google Gemini translation provider."""

import asyncio
import logging

import aiohttp

from languagebridge.config import LLMConfig
from languagebridge.llm.base import TranslationContext, TranslationProvider
from languagebridge.prompt import build_system_prompt

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.0-flash"
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
MAX_RETRIES = 3
TIMEOUT_SECONDS = 10


class GeminiProvider(TranslationProvider):
    def __init__(self, config: LLMConfig) -> None:
        if not config.api_key:
            raise ValueError("Gemini provider requires an api_key")
        self._api_key = config.api_key
        self._model = config.model or DEFAULT_MODEL

    @property
    def display_name(self) -> str:
        return f"Gemini ({self._model})"

    async def translate(self, text: str, context: TranslationContext) -> str:
        system_prompt = build_system_prompt(context)
        url = f"{API_BASE}/{self._model}:generateContent?key={self._api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "maxOutputTokens": 1024,
                "temperature": 0.3,
            },
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
                            candidates = data.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get(
                                    "parts", []
                                )
                                if parts:
                                    return parts[0]["text"].strip()
                            return "[SKIP]"
                        body = await resp.text()
                        logger.warning(
                            "Gemini API error (attempt %d/%d): %d %s",
                            attempt + 1,
                            MAX_RETRIES,
                            resp.status,
                            body[:200],
                        )
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(
                    "Gemini request failed (attempt %d/%d): %s",
                    attempt + 1,
                    MAX_RETRIES,
                    e,
                )

            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2**attempt)

        logger.error("Gemini translation failed after %d attempts", MAX_RETRIES)
        return "[SKIP]"
