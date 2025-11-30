from __future__ import annotations

from typing import Any, Dict, Optional, List
import asyncio

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .base import JobRepository, Job
from ..types import Db
from ..orm.session import create_engine_from_db, session_factory
from ..orm.models import Base, RagJob


class PostgresJobRepository(JobRepository):
    def __init__(self, db: Db, table: str = "rag_jobs") -> None:
        self.db = db
        self.engine = create_engine_from_db(db)
        # Allow custom table name by overriding __tablename__ dynamically
        if RagJob.__tablename__ != table:
            RagJob.__table__.name = table  # type: ignore
        self.Session = session_factory(db)

    async def ensure(self) -> None:
        def _ensure():
            Base.metadata.create_all(self.engine, tables=[RagJob.__table__])
        await asyncio.to_thread(_ensure)

    async def enqueue(self, job_type: str, payload: Dict[str, Any]) -> int:
        await self.ensure()

        def _ins() -> int:
            with self.Session() as sess:
                job = RagJob(type=job_type, payload=payload, status="pending", attempts=0)
                sess.add(job)
                sess.commit()
                sess.refresh(job)
                return int(job.id)

        return await asyncio.to_thread(_ins)

    async def fetch_and_start(self) -> Optional[Job]:
        await self.ensure()

        def _fetch() -> Optional[Job]:
            with self.Session() as sess:
                stmt = (
                    select(RagJob)
                    .where(RagJob.status == "pending")
                    .order_by(RagJob.id)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                row = sess.execute(stmt).scalars().first()
                if row is None:
                    return None
                row.status = "processing"
                row.attempts = (row.attempts or 0) + 1
                row.started_at = func.now()
                sess.commit()
                return Job(
                    id=int(row.id),
                    type=str(row.type),
                    payload=dict(row.payload or {}),
                    status=str(row.status),
                    attempts=int(row.attempts or 0),
                    error=row.error,
                    created_at=row.created_at,
                    started_at=row.started_at,
                    finished_at=row.finished_at,
                    progress_done=row.progress_done,
                    progress_total=row.progress_total,
                    progress_note=row.progress_note,
                )

        return await asyncio.to_thread(_fetch)

    async def list(self, limit: int = 20, status: Optional[str] = None) -> List[Job]:
        await self.ensure()

        def _list() -> List[Job]:
            with self.Session() as sess:
                stmt = select(RagJob).order_by(RagJob.id.desc()).limit(int(limit))
                if status:
                    stmt = select(RagJob).where(RagJob.status == status).order_by(RagJob.id.desc()).limit(int(limit))
                rows = sess.execute(stmt).scalars().all()
                out: List[Job] = []
                for row in rows:
                    out.append(
                        Job(
                            id=int(row.id),
                            type=str(row.type),
                            payload=dict(row.payload or {}),
                            status=str(row.status),
                            attempts=int(row.attempts or 0),
                            error=row.error,
                            created_at=row.created_at,
                            started_at=row.started_at,
                            finished_at=row.finished_at,
                            progress_done=row.progress_done,
                            progress_total=row.progress_total,
                            progress_note=row.progress_note,
                        )
                    )
                return out

        return await asyncio.to_thread(_list)

    async def get(self, job_id: int) -> Optional[Job]:
        await self.ensure()

        def _get() -> Optional[Job]:
            with self.Session() as sess:
                row = sess.get(RagJob, int(job_id))
                if row is None:
                    return None
                return Job(
                    id=int(row.id),
                    type=str(row.type),
                    payload=dict(row.payload or {}),
                    status=str(row.status),
                    attempts=int(row.attempts or 0),
                    error=row.error,
                    created_at=row.created_at,
                    started_at=row.started_at,
                    finished_at=row.finished_at,
                    progress_done=row.progress_done,
                    progress_total=row.progress_total,
                    progress_note=row.progress_note,
                )

        return await asyncio.to_thread(_get)

    async def complete(self, job_id: int) -> None:
        def _run():
            with self.Session() as sess:
                row = sess.get(RagJob, int(job_id))
                if row is None:
                    return
                row.status = "completed"
                row.finished_at = func.now()
                row.error = None
                sess.commit()

        await asyncio.to_thread(_run)

    async def fail(self, job_id: int, error: str) -> None:
        def _run():
            with self.Session() as sess:
                row = sess.get(RagJob, int(job_id))
                if row is None:
                    return
                row.status = "failed"
                row.finished_at = func.now()
                row.error = error
                sess.commit()

        await asyncio.to_thread(_run)

    async def retry(self, job_id: int) -> bool:
        await self.ensure()

        def _run() -> bool:
            with self.Session() as sess:
                row = sess.get(RagJob, int(job_id))
                if row is None or row.status not in ("failed", "canceled"):
                    return False
                row.status = "pending"
                row.started_at = None
                row.finished_at = None
                row.error = None
                sess.commit()
                return True

        return await asyncio.to_thread(_run)

    async def cancel(self, job_id: int) -> bool:
        await self.ensure()

        def _run() -> bool:
            with self.Session() as sess:
                row = sess.get(RagJob, int(job_id))
                if row is None or row.status not in ("pending", "processing"):
                    return False
                row.status = "canceled"
                row.finished_at = func.now()
                if not row.error:
                    row.error = "canceled"
                sess.commit()
                return True

        return await asyncio.to_thread(_run)

    async def update_progress(self, job_id: int, *, done: int | None = None, total: int | None = None, note: str | None = None) -> None:
        await self.ensure()

        def _run():
            with self.Session() as sess:
                row = sess.get(RagJob, int(job_id))
                if row is None:
                    return
                if done is not None:
                    row.progress_done = int(done)
                if total is not None:
                    row.progress_total = int(total)
                if note is not None:
                    row.progress_note = str(note)
                sess.commit()

        await asyncio.to_thread(_run)

    async def mark_processing(self, job_id: int) -> None:
        await self.ensure()

        def _run():
            with self.Session() as sess:
                row = sess.get(RagJob, int(job_id))
                if row is None:
                    return
                row.status = "processing"
                row.started_at = func.now()
                row.attempts = (row.attempts or 0) + 1
                sess.commit()

        await asyncio.to_thread(_run)
