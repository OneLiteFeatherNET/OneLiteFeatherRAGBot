from __future__ import annotations

from rag_core import AIConfig, OpenAIProvider, OllamaProvider, AIProvider
from ..config import settings


def build_ai_provider() -> AIProvider:
    provider = (settings.ai_provider or "openai").lower()
    cfg = AIConfig(
        llm_model=settings.llm_model,
        embedding_model=settings.embed_model,
        temperature=settings.temperature,
    )

    if provider == "ollama":
        return OllamaProvider(config=cfg, base_url=settings.ollama_base_url)
    return OpenAIProvider(config=cfg)

