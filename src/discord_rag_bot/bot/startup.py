from __future__ import annotations

from ..config import settings
from ..infrastructure.ai import build_ai_provider
from .client import RagBot
from .services import BotServices
from rag_core import RAGService, VectorStoreConfig, RagConfig
from rag_core.jobs import JobStore


def build_services() -> BotServices:
    ai = build_ai_provider()
    rag = RAGService(
        vs_config=VectorStoreConfig(
            db=settings.db,
            table_name=settings.table_name,
            embed_dim=settings.embed_dim,
        ),
        rag_config=RagConfig(top_k=settings.top_k),
        ai_provider=ai,
    )
    jobs = JobStore(db=settings.db)
    jobs.ensure_table()
    return BotServices(rag=rag, job_store=jobs)


def build_bot() -> RagBot:
    services = build_services()
    return RagBot(services)
