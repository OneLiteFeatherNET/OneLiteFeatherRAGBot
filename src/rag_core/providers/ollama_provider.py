from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from llama_index.core import Settings

from .base import AIProvider, AIConfig


@dataclass(frozen=True)
class OllamaProvider(AIProvider):
    config: AIConfig
    base_url: Optional[str] = None  # e.g. http://localhost:11434

    def configure_global(self) -> None:
        # Import lazily to avoid hard dependency unless used
        from llama_index.llms.ollama import Ollama
        from llama_index.embeddings.ollama import OllamaEmbedding

        Settings.llm = Ollama(model=self.config.llm_model, temperature=self.config.temperature, base_url=self.base_url)
        Settings.embed_model = OllamaEmbedding(model_name=self.config.embedding_model, base_url=self.base_url)
