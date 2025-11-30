from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, List
import asyncio

from rag_core.tools.base import Tool, ToolResult
from ..config import settings
from rag_core.etl.artifacts import LocalArtifactStore
from rag_core.etl.artifacts_s3 import S3ArtifactStore, S3Unavailable
from rag_core.etl.pipeline import build_manifest
from rag_core.ingestion.web import UrlSource, WebsiteCrawlerSource, SitemapSource
from rag_core.ingestion.github import GitRepoSource, GitHubOrgSource
from rag_core.ingestion.filesystem import FilesystemSource
from rag_core.ingestion.chunked import ChunkingSource


def _artifact_store():
    backend = (getattr(settings, "etl_staging_backend", "local") or "local").lower()
    if backend == "s3":
        if not getattr(settings, "s3_staging_bucket", None):
            raise RuntimeError("S3 staging selected but APP_S3_STAGING_BUCKET not set")
        try:
            return S3ArtifactStore(
                bucket=settings.s3_staging_bucket,  # type: ignore[arg-type]
                prefix=getattr(settings, "s3_staging_prefix", "rag-artifacts"),
                region=getattr(settings, "s3_region", None),
                endpoint_url=getattr(settings, "s3_endpoint_url", None),
                access_key_id=getattr(settings, "s3_access_key_id", None),
                secret_access_key=getattr(settings, "s3_secret_access_key", None),
            )
        except S3Unavailable as e:
            raise RuntimeError(str(e))
    return LocalArtifactStore(root=__import__("pathlib").Path(getattr(settings, "etl_staging_dir", ".staging")))


@dataclass
class _QueueCtx:
    enqueue: Any  # callable (type handled at runtime)


class _BaseQueueTool(Tool):
    name: str = "queue.base"
    description: str = "Base queue tool"

    def __init__(self, enqueue_callable: Any) -> None:
        self._ctx = _QueueCtx(enqueue=enqueue_callable)

    def _put_manifest_and_enqueue(self, manifest: dict) -> ToolResult:
        store = _artifact_store()
        key = store.put_manifest(manifest)
        payload = {"artifact_key": key}
        # Enqueue on ingest queue
        job_id = asyncio.run(self._ctx.enqueue("ingest", payload))
        return ToolResult(content=f"queued ingest job #{job_id} (artifact={key})", raw={"job_id": job_id, "artifact_key": key})


class QueueWebUrlTool(_BaseQueueTool):
    name = "queue.web.url"
    description = "Queue specific URLs for indexing. payload: { urls: string[] }"

    def run(self, payload: Dict[str, Any]) -> ToolResult:
        urls: List[str] = [str(u) for u in (payload.get("urls") or []) if str(u).strip()]
        if not urls:
            return ToolResult(content="no urls provided")
        source = UrlSource(urls=urls)
        manifest = asyncio.run(asyncio.to_thread(build_manifest, source))
        return self._put_manifest_and_enqueue(manifest)


class QueueWebsiteTool(_BaseQueueTool):
    name = "queue.web.website"
    description = "Queue a website crawl. payload: { start_url: string, allowed_prefixes?: string[], max_pages?: number }"

    def run(self, payload: Dict[str, Any]) -> ToolResult:
        start_url = str(payload.get("start_url") or "").strip()
        if not start_url:
            return ToolResult(content="start_url required")
        allowed = [str(p) for p in (payload.get("allowed_prefixes") or []) if str(p).strip()] or [start_url]
        max_pages = int(payload.get("max_pages") or 200)
        source = WebsiteCrawlerSource(start_urls=[start_url], allowed_prefixes=allowed, max_pages=max_pages)
        manifest = asyncio.run(asyncio.to_thread(build_manifest, source))
        return self._put_manifest_and_enqueue(manifest)


class QueueSitemapTool(_BaseQueueTool):
    name = "queue.web.sitemap"
    description = "Queue a sitemap. payload: { sitemap_url: string, limit?: number }"

    def run(self, payload: Dict[str, Any]) -> ToolResult:
        sitemap_url = str(payload.get("sitemap_url") or "").strip()
        if not sitemap_url:
            return ToolResult(content="sitemap_url required")
        limit = payload.get("limit")
        lim = int(limit) if isinstance(limit, (int, str)) and str(limit).isdigit() else None
        source = SitemapSource(sitemap_url=sitemap_url, limit=lim)
        manifest = asyncio.run(asyncio.to_thread(build_manifest, source))
        return self._put_manifest_and_enqueue(manifest)


class QueueGithubRepoTool(_BaseQueueTool):
    name = "queue.github.repo"
    description = "Queue a GitHub repository. payload: { repo: string, branch?: string, exts?: string[], chunk_size?: number, chunk_overlap?: number }"

    def run(self, payload: Dict[str, Any]) -> ToolResult:
        repo = str(payload.get("repo") or "").strip()
        if not repo:
            return ToolResult(content="repo url required")
        branch = payload.get("branch")
        exts = payload.get("exts")
        exts_list = [str(e) for e in exts] if isinstance(exts, list) else getattr(settings, "ingest_exts", [])
        chunk_size = payload.get("chunk_size")
        chunk_overlap = payload.get("chunk_overlap") or 200
        source = GitRepoSource(repo_url=repo, branch=str(branch) if branch else None, exts=exts_list)
        if chunk_size:
            source = ChunkingSource(source=source, chunk_size=int(chunk_size), overlap=int(chunk_overlap))
        manifest = asyncio.run(asyncio.to_thread(build_manifest, source))
        return self._put_manifest_and_enqueue(manifest)


class QueueLocalDirTool(_BaseQueueTool):
    name = "queue.local.dir"
    description = "Queue a local directory. payload: { repo_root: string, repo_url: string, exts?: string[], chunk_size?: number, chunk_overlap?: number }"

    def run(self, payload: Dict[str, Any]) -> ToolResult:
        root = str(payload.get("repo_root") or "").strip()
        repo_url = str(payload.get("repo_url") or "").strip()
        if not root or not repo_url:
            return ToolResult(content="repo_root and repo_url required")
        exts = payload.get("exts")
        exts_list = [str(e) for e in exts] if isinstance(exts, list) else getattr(settings, "ingest_exts", [])
        chunk_size = payload.get("chunk_size")
        chunk_overlap = payload.get("chunk_overlap") or 200
        source = FilesystemSource(repo_root=__import__("pathlib").Path(root), repo_url=repo_url, exts=exts_list)
        if chunk_size:
            source = ChunkingSource(source=source, chunk_size=int(chunk_size), overlap=int(chunk_overlap))
        manifest = asyncio.run(asyncio.to_thread(build_manifest, source))
        return self._put_manifest_and_enqueue(manifest)

