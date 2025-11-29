from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core import SimpleDirectoryReader
from llama_index.core.schema import Document
from llama_index.vector_stores.postgres import PGVectorStore

from .types import Db
from .providers.base import AIProvider


@dataclass(frozen=True)
class RagResult:
    answer: str
    sources: list[str]


@dataclass(frozen=True)
class VectorStoreConfig:
    db: Db
    table_name: str
    embed_dim: int


@dataclass(frozen=True)
class RagConfig:
    top_k: int = 6


DEFAULT_EXTS = [
    ".md",
    ".py",
    ".yml",
    ".yaml",
    ".toml",
    ".json",
    ".txt",
]


class RAGService:
    def __init__(
        self,
        vs_config: VectorStoreConfig,
        rag_config: RagConfig | None = None,
        ai_provider: AIProvider | None = None,
    ) -> None:
        self.vs_config = vs_config
        self.rag_config = rag_config or RagConfig()
        self.ai_provider = ai_provider
        if self.ai_provider is not None:
            self.ai_provider.configure_global()

        self._vector_store = PGVectorStore.from_params(
            database=vs_config.db.database,
            host=vs_config.db.host,
            port=vs_config.db.port,
            user=vs_config.db.user,
            password=vs_config.db.password,
            table_name=vs_config.table_name,
            embed_dim=vs_config.embed_dim,
        )
        self._storage_context = StorageContext.from_defaults(vector_store=self._vector_store)
        self._index = VectorStoreIndex.from_vector_store(
            vector_store=self._vector_store,
            storage_context=self._storage_context,
        )
        self._qe = self._index.as_query_engine(similarity_top_k=self.rag_config.top_k)

    def query(self, question: str) -> RagResult:
        response = self._qe.query(question)
        return RagResult(answer=str(response), sources=self._extract_sources(response))

    def index_directory(
        self,
        repo_root: Path,
        repo_url: str,
        required_exts: Iterable[str] | None = None,
    ) -> None:
        exts = list(required_exts) if required_exts is not None else list(DEFAULT_EXTS)

        def meta_fn(filename: str):
            rel = str(Path(filename).relative_to(repo_root))
            return {
                "repo": repo_url,
                "file_path": rel,
                "source_url": f"{repo_url}/blob/main/{rel}",
            }

        docs = SimpleDirectoryReader(
            input_dir=str(repo_root),
            recursive=True,
            required_exts=exts,
            file_metadata=meta_fn,
            filename_as_id=True,
        ).load_data()

        VectorStoreIndex.from_documents(
            docs,
            storage_context=self._storage_context,
            show_progress=True,
        )

    def index_items(self, items: Iterable[tuple[str, dict]]) -> None:
        """Index an iterable of (text, metadata) tuples into the vector store."""
        docs = [Document(text=t, metadata=m) for (t, m) in items]
        if not docs:
            return
        VectorStoreIndex.from_documents(
            docs,
            storage_context=self._storage_context,
            show_progress=True,
        )

    @staticmethod
    def _extract_sources(response) -> list[str]:
        out: list[str] = []
        for sn in getattr(response, "source_nodes", [])[:6]:
            md = getattr(sn.node, "metadata", {}) or {}
            url = md.get("source_url") or md.get("file_path")
            if url and url not in out:
                out.append(url)
        return out
