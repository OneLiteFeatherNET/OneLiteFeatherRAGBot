from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable, Dict


Text = str
Metadata = Dict[str, object]


@dataclass(frozen=True)
class IngestItem:
    doc_id: str
    text: Text
    metadata: Metadata
    checksum: str


class IngestionSource(ABC):
    @abstractmethod
    def stream(self) -> Iterable[IngestItem]:
        """Yield items with stable doc_id, text, metadata, and checksum."""
        raise NotImplementedError
