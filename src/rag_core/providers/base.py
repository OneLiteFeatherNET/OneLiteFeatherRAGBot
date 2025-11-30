from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class AIConfig:
    llm_model: str
    embedding_model: str
    temperature: float = 0.1
    embed_backend: str = "openai"  # openai|ollama
    system_prompt: str | None = None


class AIProvider(ABC):
    @abstractmethod
    def configure_global(self) -> None:  # sets LlamaIndex global Settings
        raise NotImplementedError

    @abstractmethod
    def create_llm(self, *, system_prompt: str | None = None):  # pragma: no cover
        """Create an LLM instance honoring optional system prompt override."""
        raise NotImplementedError
