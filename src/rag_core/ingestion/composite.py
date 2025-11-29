from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from .base import IngestionSource, IngestItem


@dataclass
class CompositeSource(IngestionSource):
    sources: List[IngestionSource]

    def stream(self) -> Iterable[IngestItem]:
        for src in self.sources:
            yield from src.stream()
