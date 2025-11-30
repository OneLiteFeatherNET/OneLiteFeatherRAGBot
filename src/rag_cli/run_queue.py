from __future__ import annotations

import time
import argparse
import logging

from discord_rag_bot.config import settings
from discord_rag_bot.infrastructure.ai import build_ai_provider
from rag_core import RAGService, VectorStoreConfig, RagConfig
from rag_core.jobs import JobStore
from rag_core.logging import setup_logging
from rag_core.ingestion.chunked import ChunkingSource
from rag_cli.config_loader import config_from_dict, composite_from_config


def build_service() -> RAGService:
    vs = VectorStoreConfig(
        db=settings.db,
        table_name=settings.table_name,
        embed_dim=settings.embed_dim,
    )
    ai = build_ai_provider()
    return RAGService(vs_config=vs, rag_config=RagConfig(top_k=settings.top_k), ai_provider=ai)


def process_one(job_store: JobStore, service: RAGService) -> bool:
    log = logging.getLogger(__name__)
    job = job_store.fetch_and_start()
    if not job:
        return False
    log.info("Processing job #%d type=%s", job.id, job.type)
    try:
        cfg = config_from_dict(job.payload)
        source = composite_from_config(cfg)
        if cfg.chunk_size:
            source = ChunkingSource(source=source, chunk_size=cfg.chunk_size or 0, overlap=cfg.chunk_overlap or 200)

        def progress(stage: str, *, done: int | None = None, total: int | None = None, note: str | None = None):
            try:
                import asyncio

                asyncio.run(job_store.update_progress_async(job.id, done=done, total=total, note=note))
            except Exception:
                pass

        progress("scanning", note="starting")
        service.index_items(source.stream(), force=False, progress=lambda stage, **kw: progress(stage, **kw))
        progress("done", note="completed")
        job_store.complete(job.id)
        log.info("Job #%d completed", job.id)
    except Exception as e:
        job_store.fail(job.id, str(e))
        log.exception("Job #%d failed: %s", job.id, e)
    return True


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Process pending indexing jobs from the queue")
    parser.add_argument("--once", action="store_true", help="Process a single job and exit")
    parser.add_argument("--poll", type=float, default=5.0, help="Polling interval in seconds")
    args = parser.parse_args()

    job_store = JobStore(db=settings.db)
    job_store.ensure_table()
    service = build_service()

    if args.once:
        processed = process_one(job_store, service)
        if not processed:
            print("No pending jobs.")
        return

    while True:
        processed = process_one(job_store, service)
        if not processed:
            time.sleep(args.poll)
