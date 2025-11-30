from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from datetime import datetime


@dataclass
class Job:
    id: int
    type: str
    payload: Dict[str, Any]
    status: str
    attempts: int
    error: Optional[str]
    created_at: Optional[datetime]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    progress_done: Optional[int] = None
    progress_total: Optional[int] = None
    progress_note: Optional[str] = None


class JobRepository(ABC):
    @abstractmethod
    async def ensure(self) -> None:  # pragma: no cover
        ...

    @abstractmethod
    async def enqueue(self, job_type: str, payload: Dict[str, Any]) -> int:  # pragma: no cover
        ...

    @abstractmethod
    async def fetch_and_start(self) -> Optional[Job]:  # pragma: no cover
        ...

    @abstractmethod
    async def list(self, limit: int = 20, status: Optional[str] = None) -> List[Job]:  # pragma: no cover
        ...

    @abstractmethod
    async def get(self, job_id: int) -> Optional[Job]:  # pragma: no cover
        ...

    @abstractmethod
    async def complete(self, job_id: int) -> None:  # pragma: no cover
        ...

    @abstractmethod
    async def fail(self, job_id: int, error: str) -> None:  # pragma: no cover
        ...

    @abstractmethod
    async def retry(self, job_id: int) -> bool:  # pragma: no cover
        ...

    @abstractmethod
    async def cancel(self, job_id: int) -> bool:  # pragma: no cover
        ...

    @abstractmethod
    async def update_progress(self, job_id: int, *, done: int | None = None, total: int | None = None, note: str | None = None) -> None:  # pragma: no cover
        ...

