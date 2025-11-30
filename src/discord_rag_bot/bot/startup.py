from __future__ import annotations

from ..config import settings
from ..infrastructure.ai import build_ai_provider
from .client import RagBot
from .services import BotServices
from rag_core import RAGService, VectorStoreConfig, RagConfig
import asyncio
from rag_core.db.postgres_jobs import PostgresJobRepository
from rag_core.db.base import JobRepository
from rag_core.tools.registry import ToolsRegistry


def build_services() -> BotServices:
    ai = build_ai_provider()
    rag = RAGService(
        vs_config=VectorStoreConfig(
            db=settings.db,
            table_name=settings.table_name,
            embed_dim=settings.embed_dim,
        ),
        rag_config=RagConfig(
            top_k=settings.top_k,
            fallback_to_llm=settings.rag_fallback_to_llm,
            mix_llm_with_rag=settings.rag_mix_llm_with_rag,
            mix_threshold=settings.rag_mix_threshold,
            score_kind=settings.rag_score_kind,
        ),
        ai_provider=ai,
    )
    job_repo: JobRepository = PostgresJobRepository(db=settings.db)
    # Ensure schema exists
    asyncio.run(job_repo.ensure())
    tools = ToolsRegistry()
    return BotServices(rag=rag, job_repo=job_repo, tools=tools)


def build_bot() -> RagBot:
    services = build_services()
    return RagBot(services)
