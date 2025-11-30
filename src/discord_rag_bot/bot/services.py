from __future__ import annotations

from dataclasses import dataclass

from rag_core import RAGService
from rag_core.tools.registry import ToolsRegistry
from rag_core.db.base import JobRepository
from ..job_repo import JobRepoFactory


@dataclass
class BotServices:
    rag: RAGService
    job_repo_factory: "JobRepoFactory"
    job_repo_default: JobRepository
    tools: ToolsRegistry
