from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from discord_rag_bot.config import settings
from rag_core import RAGService, VectorStoreConfig, RagConfig, DEFAULT_EXTS
from rag_core.ingestion.base import IngestionSource
from rag_core.ingestion.filesystem import FilesystemSource
from rag_core.ingestion.composite import CompositeSource
from rag_core.ingestion.chunked import ChunkingSource
from rag_cli.config_loader import load_config, composite_from_config
from discord_rag_bot.infrastructure.ai import build_ai_provider
from rag_core.logging import setup_logging
import logging


def build_service() -> RAGService:
    vs = VectorStoreConfig(
        db=settings.db,
        table_name=settings.table_name,
        embed_dim=settings.embed_dim,
    )
    ai = build_ai_provider()
    return RAGService(vs_config=vs, rag_config=RagConfig(top_k=settings.top_k), ai_provider=ai)


def main() -> None:
    setup_logging()
    log = logging.getLogger(__name__)
    parser = argparse.ArgumentParser(description="Index content sources into pgvector for RAG.")
    parser.add_argument("repo_root", nargs="?", type=Path, help="Local path to repository root (legacy mode)")
    parser.add_argument("repo_url", nargs="?", type=str, help="Public URL of the repository (legacy mode)")
    parser.add_argument("--config", type=Path, default=None, help="YAML config describing multiple sources")
    parser.add_argument(
        "--ext",
        dest="exts",
        action="append",
        default=None,
        help="File extension to include (can be specified multiple times). Default uses built-in set (legacy mode).",
    )
    parser.add_argument("--chunk-size", type=int, default=None, help="Enable content chunking with this max size (characters)")
    parser.add_argument("--chunk-overlap", type=int, default=200, help="Chunk overlap in characters (when chunking)")
    args = parser.parse_args()

    service = build_service()

    if args.config:
        cfg = load_config(args.config)
        source = composite_from_config(cfg)
        if (cfg.chunk_size or args.chunk_size):
            size = args.chunk_size or cfg.chunk_size or 0
            overlap = args.chunk_overlap if args.chunk_overlap is not None else (cfg.chunk_overlap or 200)
            source = ChunkingSource(source=source, chunk_size=size, overlap=overlap)
        log.info("Starting indexing from config: %s", args.config)
        service.index_items(source.stream())
    else:
        if not args.repo_root or not args.repo_url:
            parser.error("Either provide --config or both repo_root and repo_url")
        required_exts = args.exts if args.exts else DEFAULT_EXTS
        source = FilesystemSource(repo_root=args.repo_root, repo_url=args.repo_url, exts=required_exts)
        if args.chunk_size:
            source = ChunkingSource(source=source, chunk_size=args.chunk_size, overlap=args.chunk_overlap)
        log.info("Starting indexing for repo: root=%s url=%s", args.repo_root, args.repo_url)
        service.index_items(source.stream())

    print("Indexing completed.")
