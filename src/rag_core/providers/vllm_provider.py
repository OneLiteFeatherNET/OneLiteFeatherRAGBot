from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from llama_index.core import Settings
from llama_index.llms.openai import OpenAI

from .base import AIProvider, AIConfig


@dataclass(frozen=True)
class VLLMProvider(AIProvider):
    config: AIConfig
    base_url: str
    api_key: Optional[str] = None  # some vLLM deployments ignore API key
    ollama_base_url: Optional[str] = None

    def configure_global(self) -> None:
        # LLM via OpenAI-compatible API (vLLM)
        Settings.llm = OpenAI(
            model=self.config.llm_model,
            temperature=self.config.temperature,
            base_url=self.base_url,
            api_key=self.api_key or "EMPTY",
        )

        # Embeddings backend can be chosen via config.embed_backend
        if self.config.embed_backend == "ollama":
            # Lazy import to avoid requiring package when unused
            from llama_index.embeddings.ollama import OllamaEmbedding

            Settings.embed_model = OllamaEmbedding(
                model_name=self.config.embedding_model,
                base_url=self.ollama_base_url,
            )
        else:
            from llama_index.embeddings.openai import OpenAIEmbedding

            Settings.embed_model = OpenAIEmbedding(model=self.config.embedding_model)

