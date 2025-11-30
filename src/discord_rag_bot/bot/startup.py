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
from ..infrastructure.config_store import ensure_store as ensure_config_store
from ..infrastructure.config_store import migrate_prompts_files_to_db
from ..infrastructure.config_store import ensure_store as ensure_config_store


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
    backend = (getattr(settings, "job_backend", "postgres") or "postgres").lower()
    if backend == "postgres":
        job_repo = PostgresJobRepository(db=settings.db)
    elif backend == "redis":
        raise ValueError("Redis backend is no longer supported. Use postgres or rabbitmq.")
    elif backend == "rabbitmq":
        from rag_core.db.rabbitmq_jobs import RabbitMQJobRepository

        if not getattr(settings, "rabbitmq_url", None):
            raise ValueError("APP_RABBITMQ_URL is required when APP_JOB_BACKEND=rabbitmq")
        job_repo = RabbitMQJobRepository(url=settings.rabbitmq_url, queue=getattr(settings, "rabbitmq_queue", "rag_jobs"), db=settings.db)
    else:
        raise ValueError(f"Unknown APP_JOB_BACKEND: {backend}")
    # Ensure schema exists
    asyncio.run(job_repo.ensure())
    # Ensure config store (DB) exists and migrate file-based prompts automatically
    if (getattr(settings, "config_backend", "db") or "db").lower() == "db":
        try:
            ensure_config_store()
            # Auto-migrate .staging prompts into DB (one-time, best-effort)
            migrate_prompts_files_to_db(delete_files=True)
        except Exception:
            pass
    # Ensure config store (DB) exists if enabled
    if (getattr(settings, "config_backend", "db") or "db").lower() == "db":
        try:
            ensure_config_store()
        except Exception:
            pass
    tools = ToolsRegistry()
    return BotServices(rag=rag, job_repo=job_repo, tools=tools)


def build_bot() -> RagBot:
    services = build_services()
    return RagBot(services)
