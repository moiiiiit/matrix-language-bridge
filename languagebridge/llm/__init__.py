"""LLM provider implementations for translation."""

from languagebridge.config import LLMConfig
from languagebridge.llm.anthropic import AnthropicProvider
from languagebridge.llm.base import TranslationContext, TranslationProvider
from languagebridge.llm.gemini import GeminiProvider
from languagebridge.llm.ollama import OllamaProvider
from languagebridge.llm.openai import OpenAIProvider

__all__ = [
    "TranslationProvider",
    "TranslationContext",
    "create_provider",
]

_PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
}


def create_provider(config: LLMConfig) -> TranslationProvider:
    """Create a translation provider from config."""
    cls = _PROVIDERS[config.provider]
    return cls(config)
