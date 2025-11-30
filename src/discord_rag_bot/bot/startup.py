from __future__ import annotations

from ..config import settings
from ..infrastructure.ai import build_ai_provider
from ..job_repo import JobRepoFactory
from .client import RagBot
from .services import BotServices
from rag_core import RAGService, VectorStoreConfig, RagConfig
import asyncio
from rag_core.tools.registry import ToolsRegistry
from ..infrastructure.config_store import ensure_store as ensure_config_store
from ..infrastructure.config_store import migrate_prompts_files_to_db
from ..infrastructure.memory_service import build_memory_service
from ..tools.queue_tools import (
    QueueWebUrlTool,
    QueueWebsiteTool,
    QueueSitemapTool,
    QueueGithubRepoTool,
    QueueLocalDirTool,
    QueueGithubOrgTool,
    QueueGithubRepoLocalTool,
)
from ..tools.repo_tools import ListKnownReposTool, RepoReindexTool


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
    if backend == "redis":
        raise ValueError("Redis backend is no longer supported. Use postgres or rabbitmq.")
    job_repo_factory = JobRepoFactory(settings.db, backend)
    default_job_repo = job_repo_factory.get("ingest")
    asyncio.run(default_job_repo.ensure())
    # Ensure config store (DB) exists and migrate file-based prompts automatically
    if (getattr(settings, "config_backend", "db") or "db").lower() == "db":
        try:
            ensure_config_store()
            # Auto-migrate .staging prompts into DB (one-time, best-effort)
            migrate_prompts_files_to_db(delete_files=True)
        except Exception:
            pass
    # Build memory service (llamaindex-backed with persistence, fallback supported)
    memory = build_memory_service()
    tools = ToolsRegistry()
    # Register queue tools; use the default ingest repo enqueue for now
    enqueue_callable = job_repo_factory.get("ingest").enqueue
    tools.register(QueueWebUrlTool(enqueue_callable))
    tools.register(QueueWebsiteTool(enqueue_callable))
    tools.register(QueueSitemapTool(enqueue_callable))
    tools.register(QueueGithubRepoTool(enqueue_callable))
    tools.register(QueueGithubRepoLocalTool(enqueue_callable))
    tools.register(QueueLocalDirTool(enqueue_callable))
    tools.register(QueueGithubOrgTool(enqueue_callable))
    tools.register(ListKnownReposTool())
    tools.register(RepoReindexTool(enqueue_callable))
    return BotServices(rag=rag, job_repo_factory=job_repo_factory, job_repo_default=default_job_repo, tools=tools, memory=memory)


def build_bot() -> RagBot:
    services = build_services()
    return RagBot(services)
