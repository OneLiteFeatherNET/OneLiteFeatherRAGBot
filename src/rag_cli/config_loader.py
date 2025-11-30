from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

import yaml

from rag_core.ingestion.base import IngestionSource
from rag_core.ingestion.filesystem import FilesystemSource
from rag_core.ingestion.github import GitRepoSource, GitHubOrgSource
from rag_core.ingestion.composite import CompositeSource
from rag_core.ingestion.web import UrlSource, SitemapSource, WebsiteCrawlerSource


@dataclass
class IngestConfig:
    sources: List[IngestionSource]
    chunk_size: int | None = None
    chunk_overlap: int | None = None


def load_config(path: Path) -> IngestConfig:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    srcs: List[IngestionSource] = []
    for item in data.get("sources", []):
        t = (item.get("type") or "").lower()
        if t == "local_dir":
            srcs.append(
                FilesystemSource(
                    repo_root=Path(item["path"]).expanduser(),
                    repo_url=item["repo_url"],
                    exts=item.get("exts"),
                )
            )
        elif t == "github_repo":
            srcs.append(
                GitRepoSource(
                    repo_url=item["repo"],
                    branch=item.get("branch"),
                    exts=item.get("exts"),
                    token=item.get("token"),
                )
            )
        elif t == "github_org":
            srcs.append(
                GitHubOrgSource(
                    org=item["org"],
                    visibility=item.get("visibility", "all"),
                    include_archived=bool(item.get("include_archived", False)),
                    topics=item.get("topics"),
                    exts=item.get("exts"),
                    branch=item.get("branch"),
                    token=item.get("token"),
                )
            )
        else:
            raise ValueError(f"Unknown source type: {t}")

    return IngestConfig(
        sources=srcs,
        chunk_size=data.get("chunk_size"),
        chunk_overlap=data.get("chunk_overlap"),
    )


def composite_from_config(cfg: IngestConfig) -> IngestionSource:
    return CompositeSource(cfg.sources)


def config_from_dict(data: dict) -> IngestConfig:
    srcs: List[IngestionSource] = []
    for item in data.get("sources", []):
        t = (item.get("type") or "").lower()
        if t == "local_dir":
            srcs.append(
                FilesystemSource(
                    repo_root=Path(item["path"]).expanduser(),
                    repo_url=item["repo_url"],
                    exts=item.get("exts"),
                )
            )
        elif t == "github_repo":
            srcs.append(
                GitRepoSource(
                    repo_url=item["repo"],
                    branch=item.get("branch"),
                    exts=item.get("exts"),
                    token=item.get("token"),
                )
            )
        elif t == "github_org":
            srcs.append(
                GitHubOrgSource(
                    org=item["org"],
                    visibility=item.get("visibility", "all"),
                    include_archived=bool(item.get("include_archived", False)),
                    topics=item.get("topics"),
                    exts=item.get("exts"),
                    branch=item.get("branch"),
                    token=item.get("token"),
                )
            )
        elif t == "web_url":
            urls = item.get("urls") or []
            srcs.append(UrlSource(urls=list(urls)))
        elif t == "sitemap":
            srcs.append(SitemapSource(sitemap_url=item["sitemap_url"], limit=item.get("limit")))
        elif t == "website":
            srcs.append(
                WebsiteCrawlerSource(
                    start_urls=list(item.get("start_urls") or []),
                    allowed_prefixes=item.get("allowed_prefixes"),
                    max_pages=int(item.get("max_pages") or 100),
                )
            )
        else:
            raise ValueError(f"Unknown source type: {t}")

    return IngestConfig(
        sources=srcs,
        chunk_size=data.get("chunk_size"),
        chunk_overlap=data.get("chunk_overlap"),
    )
