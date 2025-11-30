from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Iterable, Optional
import threading
from llama_index.core import Settings
import logging

from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.schema import Document
from llama_index.vector_stores.postgres import PGVectorStore

from .types import Db
from .providers.base import AIProvider
from .checksums import ChecksumStore, ChecksumRecord
from .ingestion.filesystem import FilesystemSource
from .ingestion.base import IngestItem
from sqlalchemy import create_engine, select, func, MetaData, Table
from .orm.session import create_engine_from_db
from .metrics import rag_query_duration_seconds, rag_best_score, indexing_chunks_total
import time


@dataclass(frozen=True)
class RagResult:
    answer: str
    sources: list[str]
    best_score: Optional[float] = None
    score_kind: str = "similarity"


@dataclass(frozen=True)
class VectorStoreConfig:
    db: Db
    table_name: str
    embed_dim: int


@dataclass(frozen=True)
class RagConfig:
    top_k: int = 6
    fallback_to_llm: bool = True
    mix_llm_with_rag: bool = False
    mix_threshold: Optional[float] = None  # if set, compare best score to this threshold
    score_kind: str = "similarity"  # 'similarity' (higher is better) or 'distance' (lower is better)


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
        self._default_llm = Settings.llm
        self._llm_lock = threading.Lock()

        self._vector_store = PGVectorStore.from_params(
            database=vs_config.db.database,
            host=vs_config.db.host,
            port=vs_config.db.port,
            user=vs_config.db.user,
            password=vs_config.db.password,
            table_name=vs_config.table_name,
            embed_dim=vs_config.embed_dim,
        )
        # Optional LlamaIndex docstore persistence alongside PGVector
        persist_dir: Optional[Path] = None
        try:
            from discord_rag_bot.config import settings as _settings  # lazy import
            if getattr(_settings, "docstore_persist", True):
                persist_dir = Path(getattr(_settings, "docstore_dir", ".staging/llama_storage"))
                persist_dir.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            persist_dir = None
        # Optional IndexStore on Postgres via KVIndexStore
        index_store = None
        try:
            from discord_rag_bot.config import settings as _settings
            if (getattr(_settings, "indexstore_backend", "postgres") or "postgres").lower() == "postgres":
                from llama_index.core.storage.index_store.keyval_index_store import KVIndexStore
                from .kvstore_postgres import PostgresKVStore
                kv = PostgresKVStore(db=self.vs_config.db, table_name=getattr(_settings, "indexstore_table", "llama_kv"))
                index_store = KVIndexStore(kv)
        except Exception:
            index_store = None

        if persist_dir or index_store is not None:
            kwargs = {"vector_store": self._vector_store}
            if persist_dir:
                kwargs["persist_dir"] = str(persist_dir)
            if index_store is not None:
                kwargs["index_store"] = index_store
            self._storage_context = StorageContext.from_defaults(**kwargs)
        else:
            self._storage_context = StorageContext.from_defaults(vector_store=self._vector_store)
        self._index = VectorStoreIndex.from_vector_store(
            vector_store=self._vector_store,
            storage_context=self._storage_context,
        )
        self._qe = self._index.as_query_engine(similarity_top_k=self.rag_config.top_k)
        self._log.info("RAGService initialized: table=%s embed_dim=%s top_k=%s", vs_config.table_name, vs_config.embed_dim, self.rag_config.top_k)
        self._checksums = ChecksumStore(db=vs_config.db)
        self._row_count: Optional[int] = None
        # Verify existing table embedding dimension if table exists
        self._verify_embed_dim()

    def query(self, question: str, *, system_prompt: str | None = None) -> RagResult:
        t0 = time.perf_counter()
        # When no vectors exist and fallback enabled → plain LLM
        if self._row_count is None:
            self._row_count = self._get_row_count()
        if not self._row_count and self.rag_config.fallback_to_llm:
            llm = self._select_llm(system_prompt)
            llm_resp = llm.complete(question)
            rag_query_duration_seconds.observe(time.perf_counter() - t0)
            return RagResult(answer=str(llm_resp), sources=[])

        response = self._run_query_with_prompt(question, system_prompt)
        sources = self._extract_sources(response)
        text = str(response)
        best = self._best_score(response)

        # Determine best score if available
        best = self._best_score(response)
        if best is not None:
            self._log.debug("RAG best score=%s kind=%s", best, self.rag_config.score_kind)
            try:
                # For distance metrics, map to [0,1] roughly by 1/(1+d) if needed. Here we just record raw value.
                rag_best_score.observe(float(best))
            except Exception:
                pass

        # Mix in a general LLM answer based on policy
        should_mix = False
        if self.rag_config.mix_llm_with_rag:
            if not sources:
                should_mix = True
            elif self.rag_config.mix_threshold is not None and best is not None:
                if self.rag_config.score_kind == "similarity":
                    should_mix = best < float(self.rag_config.mix_threshold)
                else:  # distance
                    should_mix = best > float(self.rag_config.mix_threshold)

        if should_mix:
            llm = self._select_llm(system_prompt)
            llm_resp = llm.complete(question)
            label = os.getenv("APP_RAG_MIX_LABEL")
            if label:
                text = f"{text}\n\n{label}\n{str(llm_resp)}"
            else:
                text = f"{text}\n\n{str(llm_resp)}"

        rag_query_duration_seconds.observe(time.perf_counter() - t0)
        return RagResult(answer=text, sources=sources, best_score=best, score_kind=self.rag_config.score_kind)

    def answer_llm(self, question: str, *, system_prompt: str | None = None) -> str:
        llm = self._select_llm(system_prompt)
        resp = llm.complete(question)
        return str(resp)

    def index_directory(
        self,
        repo_root: Path,
        repo_url: str,
        required_exts: Iterable[str] | None = None,
    ) -> None:
        self._log.info("Indexing directory: root=%s url=%s", repo_root, repo_url)
        source = FilesystemSource(repo_root=repo_root, repo_url=repo_url, exts=list(required_exts) if required_exts else None)
        self.index_items(source.stream())

    def index_items(self, items: Iterable[IngestItem], *, force: bool = False, progress: Optional[callable] = None) -> None:
        """Index items with checksum skipping using a checksum store.

        progress: optional callback(stage, *, done=None, total=None, note=None)
        """
        self._log.info("Loading checksum map ...")
        existing = self._checksums.load_map()
        self._log.info("Loaded %d checksum entries", len(existing))

        to_index: list[Document] = []
        updates: list[ChecksumRecord] = []
        scanned = 0
        if progress:
            try:
                progress("scanning", done=0, total=None, note="scanning items")
            except Exception:
                pass
        for item in items:
            scanned += 1
            if not force and existing.get(item.doc_id) == item.checksum:
                continue
            md = dict(item.metadata)
            md["checksum"] = item.checksum
            to_index.append(Document(text=item.text, metadata=md, id_=item.doc_id))
            updates.append(ChecksumRecord(doc_id=item.doc_id, checksum=item.checksum))

        if not to_index:
            self._log.info("No changes detected. Skipping indexing.")
            if progress:
                try:
                    progress("filtered", done=0, total=scanned, note="no changes")
                    progress("done", done=0, total=scanned, note="no changes")
                except Exception:
                    pass
            return

        if progress:
            try:
                progress("filtered", done=len(to_index), total=scanned, note="changed/new items")
                progress("indexing", done=0, total=len(to_index), note="writing to vector store")
            except Exception:
                pass
        VectorStoreIndex.from_documents(
            to_index,
            storage_context=self._storage_context,
            show_progress=True,
        )
        # Persist docstore/index metadata if enabled
        try:
            from discord_rag_bot.config import settings as _settings
            if getattr(_settings, "docstore_persist", True):
                pdir = Path(getattr(_settings, "docstore_dir", ".staging/llama_storage"))
                self._storage_context.persist(str(pdir))
        except Exception:
            pass
        self._log.info("Indexed %d documents (chunks). Updating checksums ...", len(to_index))
        try:
            indexing_chunks_total.inc(len(to_index))
        except Exception:
            pass
        self._checksums.upsert_many(updates)
        self._log.info("Checksum update completed (%d records)", len(updates))
        if progress:
            try:
                progress("indexed", done=len(to_index), total=len(to_index), note="completed")
                progress("done", done=len(to_index), total=len(to_index), note="completed")
            except Exception:
                pass
        # Best-effort update of cached row count
        try:
            self._row_count = (self._row_count or 0) + len(to_index)
        except Exception:
            self._row_count = None

    def update_checksums(self, items: Iterable[IngestItem], *, progress: Optional[callable] = None) -> None:
        """Only update checksum records without re-indexing vectors.

        Useful for ETL checksum refresh jobs.
        """
        records: list[ChecksumRecord] = []
        total = 0
        for it in items:
            total += 1
            records.append(ChecksumRecord(doc_id=it.doc_id, checksum=it.checksum))
        if progress:
            try:
                progress("checksums", done=0, total=total, note="updating")
            except Exception:
                pass
        self._checksums.upsert_many(records)
        if progress:
            try:
                progress("done", done=total, total=total, note="checksums updated")
            except Exception:
                pass

    def _verify_embed_dim(self) -> None:
        """Ensure existing pgvector table has expected embedding dimension.

        Checks the "data_" table (used by PGVectorStore) for the embedding column typmod.
        If the table doesn't exist yet, the check is skipped. If it exists with a
        different dimension, raise a clear error with remediation steps.
        """
        table_name = f"data_{self.vs_config.table_name}"
        try:
            engine = create_engine_from_db(self.vs_config.db)
            with engine.connect() as conn:
                md = MetaData()
                try:
                    tbl = Table(table_name, md, autoload_with=engine, schema="public")
                except Exception:
                    self._log.debug("Embedding dimension check skipped (table %s not found)", table_name)
                    return
                # Reflect pgvector column type to get dimension if available
                try:
                    col = tbl.c.embedding  # type: ignore[attr-defined]
                    actual = getattr(col.type, "dim", None)
                    if actual is not None:
                        actual = int(actual)
                except Exception:
                    actual = None
                expected = int(self.vs_config.embed_dim)
                if actual is None:
                    self._log.debug("Embedding dimension check inconclusive for table %s", table_name)
                    return
                if actual != expected:
                    raise ValueError(
                        (
                            "Embedding dimension mismatch for table '%s': actual=%d expected=%d.\n"
                            "Fix options:\n"
                            "- Set APP_TABLE_NAME to a new table (e.g., '%s_%d') and re-index, or\n"
                            "- Drop existing tables (data_%s, index_%s) and re-index, or\n"
                            "- Adjust APP_EMBED_PROVIDER/APP_EMBED_MODEL/APP_EMBED_DIM to match the existing table."
                        )
                        % (
                            table_name,
                            actual,
                            expected,
                            self.vs_config.table_name,
                            expected,
                            self.vs_config.table_name,
                            self.vs_config.table_name,
                        )
                    )
                # Also cache current row count
                try:
                    self._row_count = int(conn.execute(select(func.count()).select_from(tbl)).scalar() or 0)
                except Exception:
                    self._row_count = None
        except Exception as e:
            # If anything goes wrong, log and continue; core operations may still work
            self._log.debug("Embed dimension check encountered an issue: %s", e)

    def _get_row_count(self) -> int:
        table_name = f"data_{self.vs_config.table_name}"
        try:
            engine = create_engine_from_db(self.vs_config.db)
            with engine.connect() as conn:
                md = MetaData()
                try:
                    tbl = Table(table_name, md, autoload_with=engine, schema="public")
                except Exception:
                    return 0
                return int(conn.execute(select(func.count()).select_from(tbl)).scalar() or 0)
        except Exception:
            return 0

    def _select_llm(self, system_prompt: str | None):
        if system_prompt and self.ai_provider is not None:
            try:
                return self.ai_provider.create_llm(system_prompt=system_prompt)
            except Exception:
                return self._default_llm
        return self._default_llm

    def _run_query_with_prompt(self, question: str, system_prompt: str | None):
        if not system_prompt or self.ai_provider is None:
            return self._qe.query(question)
        llm = self._select_llm(system_prompt)
        # Temporarily swap global llm in a lock to avoid races
        with self._llm_lock:
            prev = Settings.llm
            Settings.llm = llm
            try:
                return self._qe.query(question)
            finally:
                Settings.llm = prev

    def _best_score(self, response) -> Optional[float]:
        try:
            nodes = getattr(response, "source_nodes", None) or []
            scores: list[float] = []
            for sn in nodes:
                s = getattr(sn, "score", None)
                if isinstance(s, (int, float)):
                    scores.append(float(s))
            if not scores:
                return None
            if self.rag_config.score_kind == "similarity":
                return max(scores)
            return min(scores)
        except Exception:
            return None

    @staticmethod
    def _extract_sources(response) -> list[str]:
        out: list[str] = []
        for sn in getattr(response, "source_nodes", [])[:6]:
            md = getattr(sn.node, "metadata", {}) or {}
            url = md.get("source_url") or md.get("file_path")
            if url and url not in out:
                out.append(url)
        return out
