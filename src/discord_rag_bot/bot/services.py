from __future__ import annotations

from dataclasses import dataclass

from rag_core import RAGService


@dataclass
class BotServices:
    rag: RAGService

