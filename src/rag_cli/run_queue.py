from __future__ import annotations

import time
import argparse
import logging
import time as _time

from discord_rag_bot.config import settings
from discord_rag_bot.infrastructure.ai import build_ai_provider
from discord_rag_bot.job_repo import JobRepoFactory
from rag_core import RAGService, VectorStoreConfig, RagConfig
import asyncio
from pathlib import Path
from rag_core.db.base import JobRepository
from rag_core.logging import setup_logging
from rag_core.ingestion.chunked import ChunkingSource
from rag_core.etl.artifacts import LocalArtifactStore
from rag_core.etl.artifacts_s3 import S3ArtifactStore, S3Unavailable
from rag_core.etl.pipeline import items_from_manifest
from rag_cli.config_loader import config_from_dict, composite_from_config
import os
from sqlalchemy import select, delete, MetaData, Table, func
from rag_core.orm.session import create_engine_from_db


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
        t0 = _time.perf_counter()
        # If payload references a prebuilt manifest, load it
        manifest_key = job.payload.get("artifact_key")
        force_flag = bool(job.payload.get("force", False))
        if manifest_key:
            # Select artifact store (local or S3)
            backend = (getattr(settings, "etl_staging_backend", "local") or "local").lower()
            if backend == "s3":
                if not getattr(settings, "s3_staging_bucket", None):
                    raise RuntimeError("S3 staging selected but APP_S3_STAGING_BUCKET not set")
                try:
                    store = S3ArtifactStore(
                        bucket=settings.s3_staging_bucket,  # type: ignore[arg-type]
                        prefix=getattr(settings, "s3_staging_prefix", "rag-artifacts"),
                        region=getattr(settings, "s3_region", None),
                        endpoint_url=getattr(settings, "s3_endpoint_url", None),
                        access_key_id=getattr(settings, "s3_access_key_id", None),
                        secret_access_key=getattr(settings, "s3_secret_access_key", None),
                    )
                except S3Unavailable as e:
                    raise RuntimeError(str(e))
            else:
                store = LocalArtifactStore(root=Path(getattr(settings, "etl_staging_dir", ".staging")))
            manifest = store.get_manifest(manifest_key)
            items_iter = items_from_manifest(manifest)
            def progress(stage: str, *, done: int | None = None, total: int | None = None, note: str | None = None):
                try:
                    asyncio.run(job_repo.update_progress(job.id, done=done, total=total, note=note))
                except Exception:
                    pass
            if job.type == "checksum_update":
                service.update_checksums(items_iter, progress=lambda stage, **kw: progress(stage, **kw))
            elif job.type == "prune":
                # Build keep set from manifest
                keep_ids = {it.doc_id for it in items_from_manifest(manifest)}
                prune_scope = job.payload.get("prune_scope", {}) if isinstance(job.payload, dict) else {}
                table_name = f"data_{settings.table_name}"
                eng = create_engine_from_db(settings.db)
                md = MetaData()
                with eng.begin() as conn:
                    try:
                        tbl = Table(table_name, md, autoload_with=eng, schema="public")
                    except Exception:
                        progress("prune", note="vector table not found")
                        return True
                    candidates: list[str] = []
                    # metadata_repo_from_manifest -> collect repo values from manifest
                    if prune_scope.get("metadata_repo_from_manifest"):
                        repo_vals = set()
                        for it in manifest.get("items", []):
                            mdv = it.get("metadata", {}) or {}
                            rv = mdv.get("repo")
                            if rv:
                                repo_vals.add(rv)
                        if repo_vals:
                            q = select(tbl.c.node_id).where(func.jsonb_extract_path_text(tbl.c.metadata_, "repo").in_(list(repo_vals)))
                            candidates.extend([r[0] for r in conn.execute(q).all()])
                    # metadata_repo_in
                    if "metadata_repo_in" in prune_scope:
                        vals = prune_scope.get("metadata_repo_in") or []
                        if vals:
                            q = select(tbl.c.node_id).where(func.jsonb_extract_path_text(tbl.c.metadata_, "repo").in_(list(vals)))
                            candidates.extend([r[0] for r in conn.execute(q).all()])
                    # doc_id_prefixes
                    if "doc_id_prefixes" in prune_scope:
                        for pref in (prune_scope.get("doc_id_prefixes") or []):
                            like = f"{pref}%"
                            q = select(tbl.c.node_id).where(tbl.c.node_id.like(like))
                            candidates.extend([r[0] for r in conn.execute(q).all()])
                    # doc_id_in_from_manifest
                    if prune_scope.get("doc_id_in_from_manifest"):
                        candidates.extend(list(keep_ids))
                    cand_set = set(candidates)
                    to_delete = [nid for nid in cand_set if nid not in keep_ids]
                    progress("prune", total=len(cand_set), done=0, note=f"deleting {len(to_delete)}")
                    batch = 1000
                    deleted = 0
                    for i in range(0, len(to_delete), batch):
                        part = to_delete[i : i + batch]
                        if not part:
                            continue
                        conn.execute(delete(tbl).where(tbl.c.node_id.in_(part)))
                        deleted += len(part)
                        progress("prune", total=len(to_delete), done=deleted, note=f"deleted {deleted}")
            else:
                service.index_items(items_iter, force=force_flag, progress=lambda stage, **kw: progress(stage, **kw))
        else:
            cfg = config_from_dict(job.payload)
            force_flag = bool(job.payload.get("force", False))
            source = composite_from_config(cfg)
            if cfg.chunk_size:
                source = ChunkingSource(source=source, chunk_size=cfg.chunk_size or 0, overlap=cfg.chunk_overlap or 200)

            def progress(stage: str, *, done: int | None = None, total: int | None = None, note: str | None = None):
                try:
                    asyncio.run(job_repo.update_progress(job.id, done=done, total=total, note=note))
                except Exception:
                    pass

            progress("scanning", note="starting")
            if job.type == "checksum_update":
                service.update_checksums(source.stream(), progress=lambda stage, **kw: progress(stage, **kw))
            else:
                service.index_items(source.stream(), force=force_flag, progress=lambda stage, **kw: progress(stage, **kw))
        progress("done", note="completed")
        asyncio.run(job_repo.complete(job.id))
        # Metrics: duration and completed
        try:
            from rag_core.metrics import job_duration_seconds, jobs_completed_total

            job_duration_seconds.labels(type=job.type).observe(_time.perf_counter() - t0)
            jobs_completed_total.labels(status="completed", type=job.type).inc()
        except Exception:
            pass
        log.info("Job #%d completed", job.id)
    except Exception as e:
        asyncio.run(job_repo.fail(job.id, str(e)))
        try:
            from rag_core.metrics import jobs_completed_total

            jobs_completed_total.labels(status="failed", type=job.type).inc()
        except Exception:
            pass
        log.exception("Job #%d failed: %s", job.id, e)
    return True


def build_job_repo(queue_type: str) -> JobRepository:
    backend = (getattr(settings, "job_backend", "postgres") or "postgres").lower()
    if backend == "redis":
        raise ValueError("Redis backend is no longer supported. Use postgres or rabbitmq.")
    factory = JobRepoFactory(settings.db, backend)
    repo = factory.get(queue_type)
    asyncio.run(repo.ensure())
    return repo


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Process pending indexing jobs from the queue")
    parser.add_argument("--once", action="store_true", help="Process a single job and exit")
    parser.add_argument("--poll", type=float, default=5.0, help="Polling interval in seconds")
    parser.add_argument("--queue-type", type=str, default=os.getenv("APP_WORKER_QUEUE_TYPE", "ingest"), help="Queue type/job category this worker should process")
    args = parser.parse_args()

    queue_type = args.queue_type
    job_repo = build_job_repo(queue_type)
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
