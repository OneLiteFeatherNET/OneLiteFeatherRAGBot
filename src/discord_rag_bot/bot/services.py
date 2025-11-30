from __future__ import annotations

from dataclasses import dataclass

from rag_core import RAGService
from rag_core.jobs import JobStore


@dataclass
class BotServices:
    rag: RAGService
    job_store: JobStore
