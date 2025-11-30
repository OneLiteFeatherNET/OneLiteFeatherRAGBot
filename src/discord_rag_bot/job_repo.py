from __future__ import annotations

from typing import Callable, Dict, Tuple

from .config import settings
from rag_core.db.base import JobRepository
from rag_core.db.postgres_jobs import PostgresJobRepository
from rag_core.db.rabbitmq_jobs import RabbitMQJobRepository
from ..types import Db


class JobRepoFactory:
    def __init__(self, db: Db, backend: str = "postgres") -> None:
        self._db = db
        self._backend = backend.lower()
        self._cache: Dict[Tuple[str, str], JobRepository] = {}

    def get(self, job_type: str) -> JobRepository:
        queue = getattr(settings, f"job_queue_{job_type}", None) or settings.job_queue_default
        key = (self._backend, queue or "", job_type)
        if key not in self._cache:
            self._cache[key] = self._create_repo(queue)
        return self._cache[key]

    def _create_repo(self, queue_name: str | None) -> JobRepository:
        if self._backend == "rabbitmq":
            if not settings.rabbitmq_url:
                raise ValueError("APP_RABBITMQ_URL is required when APP_JOB_BACKEND=rabbitmq")
            return RabbitMQJobRepository(
                url=settings.rabbitmq_url,
                queue=queue_name or settings.rabbitmq_queue,
                db=self._db,
            )
        if self._backend == "postgres":
            return PostgresJobRepository(db=self._db)
        raise ValueError(f"Unsupported job backend: {self._backend}")
