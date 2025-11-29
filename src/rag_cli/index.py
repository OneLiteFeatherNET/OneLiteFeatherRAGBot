from __future__ import annotations

import argparse
from pathlib import Path

from discord_rag_bot.config import settings
from rag_core import RAGService, VectorStoreConfig, RagConfig, DEFAULT_EXTS
from discord_rag_bot.infrastructure.ai import build_ai_provider


def build_service() -> RAGService:
    vs = VectorStoreConfig(
        db=settings.db,
        table_name=settings.table_name,
        embed_dim=settings.embed_dim,
    )
    ai = build_ai_provider()
    return RAGService(vs_config=vs, rag_config=RagConfig(top_k=settings.top_k), ai_provider=ai)


def main() -> None:
    parser = argparse.ArgumentParser(description="Index a repository into pgvector for RAG.")
    parser.add_argument("repo_root", type=Path, help="Local path to repository root")
    parser.add_argument("repo_url", type=str, help="Public URL of the repository (for source links)")
    parser.add_argument(
        "--ext",
        dest="exts",
        action="append",
        default=None,
        help="File extension to include (can be specified multiple times). Default uses built-in set.",
    )
    args = parser.parse_args()

    service = build_service()
    required_exts = args.exts if args.exts else DEFAULT_EXTS
    service.index_directory(repo_root=args.repo_root, repo_url=args.repo_url, required_exts=required_exts)

    print("Indexing completed.")
