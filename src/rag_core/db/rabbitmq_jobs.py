from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import JobRepository, Job


class RabbitMQJobRepository(JobRepository):
    """Placeholder RabbitMQ-backed JobRepository (for future Kubernetes deployment).

    Note: This is a stub to document intended usage. A robust implementation will pair
    a durable job store (e.g. Postgres or Redis) with RabbitMQ for notifications/transport.
    The current Discord commands rely on listing and inspecting jobs; pure RabbitMQ queues
    don't support listing message metadata. Therefore, this class raises NotImplementedError
    for listing/inspection methods.
    """

    def __init__(self, url: str, queue: str = "rag_jobs") -> None:
        self.url = url
        self.queue = queue

    async def ensure(self) -> None:  # pragma: no cover - placeholder
        raise NotImplementedError("RabbitMQ backend is not yet implemented. Use Postgres or Redis for now.")

    async def enqueue(self, job_type: str, payload: Dict[str, Any]) -> int:  # pragma: no cover - placeholder
        raise NotImplementedError("RabbitMQ backend is not yet implemented. Use Postgres or Redis for now.")

    async def fetch_and_start(self) -> Optional[Job]:  # pragma: no cover - placeholder
        raise NotImplementedError("RabbitMQ backend is not yet implemented. Use Postgres or Redis for now.")

    async def list(self, limit: int = 20, status: Optional[str] = None) -> List[Job]:  # pragma: no cover - placeholder
        raise NotImplementedError("RabbitMQ backend is not yet implemented. Use Postgres or Redis for now.")

    async def get(self, job_id: int) -> Optional[Job]:  # pragma: no cover - placeholder
        raise NotImplementedError("RabbitMQ backend is not yet implemented. Use Postgres or Redis for now.")

    async def complete(self, job_id: int) -> None:  # pragma: no cover - placeholder
        raise NotImplementedError("RabbitMQ backend is not yet implemented. Use Postgres or Redis for now.")

    async def fail(self, job_id: int, error: str) -> None:  # pragma: no cover - placeholder
        raise NotImplementedError("RabbitMQ backend is not yet implemented. Use Postgres or Redis for now.")

    async def retry(self, job_id: int) -> bool:  # pragma: no cover - placeholder
        raise NotImplementedError("RabbitMQ backend is not yet implemented. Use Postgres or Redis for now.")

    async def cancel(self, job_id: int) -> bool:  # pragma: no cover - placeholder
        raise NotImplementedError("RabbitMQ backend is not yet implemented. Use Postgres or Redis for now.")

    async def update_progress(self, job_id: int, *, done: int | None = None, total: int | None = None, note: str | None = None) -> None:  # pragma: no cover - placeholder
        raise NotImplementedError("RabbitMQ backend is not yet implemented. Use Postgres or Redis for now.")

