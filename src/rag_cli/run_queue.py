from __future__ import annotations

import time
import argparse
import logging

from discord_rag_bot.config import settings
from discord_rag_bot.infrastructure.ai import build_ai_provider
from rag_core import RAGService, VectorStoreConfig, RagConfig
import asyncio
from pathlib import Path
from rag_core.db.postgres_jobs import PostgresJobRepository
from rag_core.db.base import JobRepository
from rag_core.logging import setup_logging
from rag_core.ingestion.chunked import ChunkingSource
from rag_core.etl.artifacts import LocalArtifactStore
from rag_core.etl.pipeline import items_from_manifest
from rag_cli.config_loader import config_from_dict, composite_from_config


def build_service() -> RAGService:
    vs = VectorStoreConfig(
        db=settings.db,
        table_name=settings.table_name,
        embed_dim=settings.embed_dim,
    )
    ai = build_ai_provider()
    return RAGService(vs_config=vs, rag_config=RagConfig(top_k=settings.top_k), ai_provider=ai)


def process_one(job_repo: JobRepository, service: RAGService) -> bool:
    log = logging.getLogger(__name__)
    job = asyncio.run(job_repo.fetch_and_start())
    if not job:
        return False
    log.info("Processing job #%d type=%s", job.id, job.type)
    try:
        # If payload references a prebuilt manifest, load it and index; otherwise use config sources
        manifest_key = job.payload.get("artifact_key")
        if manifest_key:
            store = LocalArtifactStore(root=Path(getattr(settings, "etl_staging_dir", ".staging")))
            manifest = store.get_manifest(manifest_key)
            items_iter = items_from_manifest(manifest)
            def progress(stage: str, *, done: int | None = None, total: int | None = None, note: str | None = None):
                try:
                    asyncio.run(job_repo.update_progress(job.id, done=done, total=total, note=note))
                except Exception:
                    pass
            service.index_items(items_iter, force=False, progress=lambda stage, **kw: progress(stage, **kw))
        else:
            cfg = config_from_dict(job.payload)
            source = composite_from_config(cfg)
            if cfg.chunk_size:
                source = ChunkingSource(source=source, chunk_size=cfg.chunk_size or 0, overlap=cfg.chunk_overlap or 200)

            def progress(stage: str, *, done: int | None = None, total: int | None = None, note: str | None = None):
                try:
                    asyncio.run(job_repo.update_progress(job.id, done=done, total=total, note=note))
                except Exception:
                    pass

            progress("scanning", note="starting")
            service.index_items(source.stream(), force=False, progress=lambda stage, **kw: progress(stage, **kw))
        progress("done", note="completed")
        asyncio.run(job_repo.complete(job.id))
        log.info("Job #%d completed", job.id)
    except Exception as e:
        asyncio.run(job_repo.fail(job.id, str(e)))
        log.exception("Job #%d failed: %s", job.id, e)
    return True


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Process pending indexing jobs from the queue")
    parser.add_argument("--once", action="store_true", help="Process a single job and exit")
    parser.add_argument("--poll", type=float, default=5.0, help="Polling interval in seconds")
    args = parser.parse_args()

    job_repo: JobRepository = PostgresJobRepository(db=settings.db)
    asyncio.run(job_repo.ensure())
    service = build_service()

    if args.once:
        processed = process_one(job_repo, service)
        if not processed:
            print("No pending jobs.")
        return

    while True:
        processed = process_one(job_repo, service)
        if not processed:
            time.sleep(args.poll)
