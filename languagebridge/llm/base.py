"""Abstract base class for LLM translation providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TranslationContext:
    family_name: str
    source_language_hint: str
    target_language: str
    prompt_appendix: str = ""
    preserve_terms: list[str] = field(default_factory=list)
    dialect: str | None = None
    tone: str = "casual"


class TranslationProvider(ABC):
    @abstractmethod
    async def translate(self, text: str, context: TranslationContext) -> str:
        """Return translated text, or '[SKIP]' if no translation needed."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for startup messages."""
        ...
