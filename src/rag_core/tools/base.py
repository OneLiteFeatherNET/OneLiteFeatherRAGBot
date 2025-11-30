from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class ToolResult:
    content: str
    raw: Any | None = None


class Tool(ABC):
    name: str
    description: str

    @abstractmethod
    def run(self, payload: Dict[str, Any]) -> ToolResult:  # pragma: no cover
        raise NotImplementedError

