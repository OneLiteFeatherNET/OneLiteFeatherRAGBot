from __future__ import annotations

from dataclasses import dataclass

from rag_core import RAGService
from rag_core.tools.registry import ToolsRegistry
from rag_core.db.base import JobRepository


@dataclass
class BotServices:
    rag: RAGService
    job_repo: JobRepository
    tools: ToolsRegistry
