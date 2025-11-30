from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import logging

from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.schema import Document
from llama_index.vector_stores.postgres import PGVectorStore

from .types import Db
from .providers.base import AIProvider
from .checksums import ChecksumStore, ChecksumRecord
from .ingestion.filesystem import FilesystemSource
from .ingestion.base import IngestItem


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
        self._log = logging.getLogger(__name__)
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
        self._log.info("RAGService initialized: table=%s embed_dim=%s top_k=%s", vs_config.table_name, vs_config.embed_dim, self.rag_config.top_k)
        self._checksums = ChecksumStore(db=vs_config.db)

    def query(self, question: str) -> RagResult:
        response = self._qe.query(question)
        return RagResult(answer=str(response), sources=self._extract_sources(response))

    def index_directory(
        self,
        repo_root: Path,
        repo_url: str,
        required_exts: Iterable[str] | None = None,
    ) -> None:
        self._log.info("Indexing directory: root=%s url=%s", repo_root, repo_url)
        source = FilesystemSource(repo_root=repo_root, repo_url=repo_url, exts=list(required_exts) if required_exts else None)
        self.index_items(source.stream())

    def index_items(self, items: Iterable[IngestItem]) -> None:
        """Index items with checksum skipping using a checksum store."""
        self._log.info("Loading checksum map ...")
        existing = self._checksums.load_map()
        self._log.info("Loaded %d checksum entries", len(existing))

        to_index: list[Document] = []
        updates: list[ChecksumRecord] = []
        for item in items:
            if existing.get(item.doc_id) == item.checksum:
                continue
            md = dict(item.metadata)
            md["checksum"] = item.checksum
            to_index.append(Document(text=item.text, metadata=md, id_=item.doc_id))
            updates.append(ChecksumRecord(doc_id=item.doc_id, checksum=item.checksum))

        if not to_index:
            self._log.info("No changes detected. Skipping indexing.")
            return

        VectorStoreIndex.from_documents(
            to_index,
            storage_context=self._storage_context,
            show_progress=True,
        )
        self._log.info("Indexed %d documents (chunks). Updating checksums ...", len(to_index))
        self._checksums.upsert_many(updates)
        self._log.info("Checksum update completed (%d records)", len(updates))

    @staticmethod
    def _extract_sources(response) -> list[str]:
        out: list[str] = []
        for sn in getattr(response, "source_nodes", [])[:6]:
            md = getattr(sn.node, "metadata", {}) or {}
            url = md.get("source_url") or md.get("file_path")
            if url and url not in out:
                out.append(url)
        return out
