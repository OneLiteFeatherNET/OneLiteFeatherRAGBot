from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable, Iterator, Tuple, Dict


Text = str
Metadata = Dict[str, object]
Item = Tuple[Text, Metadata]


class IngestionSource(ABC):
    @abstractmethod
    def stream(self) -> Iterable[Item]:
        """Yield (text, metadata) tuples."""
        raise NotImplementedError

