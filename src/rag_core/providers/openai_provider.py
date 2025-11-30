from __future__ import annotations

from dataclasses import dataclass
from llama_index.core import Settings
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding

from .base import AIProvider, AIConfig


@dataclass(frozen=True)
class OpenAIProvider(AIProvider):
    config: AIConfig

    def configure_global(self) -> None:
        Settings.llm = OpenAI(
            model=self.config.llm_model,
            temperature=self.config.temperature,
            system_prompt=self.config.system_prompt,
        )
        Settings.embed_model = OpenAIEmbedding(model=self.config.embedding_model)

    def create_llm(self, *, system_prompt: str | None = None):
        return OpenAI(
            model=self.config.llm_model,
            temperature=self.config.temperature,
            system_prompt=system_prompt if system_prompt is not None else self.config.system_prompt,
        )
