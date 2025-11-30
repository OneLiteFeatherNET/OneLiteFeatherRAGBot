from __future__ import annotations

from rag_core import AIConfig, OpenAIProvider, OllamaProvider, VLLMProvider, AIProvider
from ..config import settings


def build_ai_provider() -> AIProvider:
    provider = (settings.ai_provider or "openai").lower()
    cfg = AIConfig(
        llm_model=settings.llm_model,
        embedding_model=settings.embed_model,
        temperature=settings.temperature,
        embed_backend=(settings.embed_provider or "openai").lower(),
    )

    if provider == "ollama":
        return OllamaProvider(config=cfg, base_url=settings.ollama_base_url)
    if provider == "vllm":
        return VLLMProvider(
            config=cfg,
            base_url=settings.vllm_base_url or "http://localhost:8000/v1",
            api_key=settings.vllm_api_key,
            ollama_base_url=settings.ollama_base_url,
        )
    return OpenAIProvider(config=cfg)
