from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import aio_pika

from .base import JobRepository, Job
from .postgres_jobs import PostgresJobRepository
from ..types import Db


class RabbitMQJobRepository(JobRepository):
    """Hybrid JobRepository using Postgres for persistence and RabbitMQ for dispatch.

    - enqueue: writes row to Postgres and publishes job_id to RabbitMQ (durable)
    - fetch_and_start: pulls one message (non-blocking) from RabbitMQ, marks job processing in Postgres, returns Job
    - complete/fail: updates Postgres and ACKs the message so it won't be re-delivered
    - retry/cancel/list/get/update_progress: operate on Postgres; retry republishes to RabbitMQ

    This design scales consumers via RabbitMQ while keeping rich job metadata in Postgres for listing and progress.
    """

    def __init__(self, url: str, queue: str = "rag_jobs", db: Optional[Db] = None) -> None:
        self.url = url
        self.queue = queue
        self._pg = PostgresJobRepository(db=db) if db is not None else None
        self._pending: dict[int, aio_pika.IncomingMessage] = {}

    async def _channel(self) -> tuple[aio_pika.RobustConnection, aio_pika.abc.AbstractChannel, aio_pika.abc.AbstractQueue]:
        conn = await aio_pika.connect_robust(self.url)
        ch = await conn.channel()
        await ch.set_qos(prefetch_count=1)
        q = await ch.declare_queue(self.queue, durable=True)
        return conn, ch, q

    async def ensure(self) -> None:
        # Ensure Postgres schema exists
        if self._pg is not None:
            await self._pg.ensure()
        # Ensure RabbitMQ queue exists
        conn, ch, _ = await self._channel()
        try:
            pass
        finally:
            await ch.close()
            await conn.close()

    async def enqueue(self, job_type: str, payload: Dict[str, Any]) -> int:
        if self._pg is None:
            raise RuntimeError("RabbitMQJobRepository requires a Postgres Db for metadata")
        job_id = await self._pg.enqueue(job_type, payload)
        conn, ch, _ = await self._channel()
        try:
            body = json.dumps({"job_id": job_id}).encode("utf-8")
            await ch.default_exchange.publish(
                aio_pika.Message(body=body, content_type="application/json", delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                routing_key=self.queue,
            )
        finally:
            await ch.close()
            await conn.close()
        return job_id

    async def fetch_and_start(self) -> Optional[Job]:
        if self._pg is None:
            raise RuntimeError("RabbitMQJobRepository requires a Postgres Db for metadata")
        conn, ch, q = await self._channel()
        try:
            msg = await q.get(no_ack=False, fail=False)  # fail=False -> return None if empty
            if msg is None:
                return None
            try:
                data = json.loads(msg.body.decode("utf-8"))
                job_id = int(data.get("job_id"))
            except Exception:
                await msg.reject(requeue=False)
                return None
            # Mark processing in Postgres (attempts++) and return job
            # Reuse PostgresJobRepository transactional update
            # We don't have a dedicated method to start by ID; emulate: get job and update fields
            job = await self._pg.get(job_id)
            if not job:
                await msg.reject(requeue=False)
                return None
            # Force status transition using Postgres repo internals via direct SQL path:
            # use list/get semantics as best-effort by calling private method via enqueue/fetch pattern
            # Simulate: set status=processing and attempts=attempts+1
            # Use a small hack: call retry() to move to pending then fetch_and_start() won't pick specifically this job.
            # Instead, update explicitly via connection
            pgdsn = self._pg._dsn()  # type: ignore[attr-defined]
            import asyncpg  # local import
            pgc = await asyncpg.connect(pgdsn)
            try:
                await pgc.execute(
                    f"UPDATE {self._pg.table} SET status='processing', started_at=NOW(), attempts = attempts + 1 WHERE id=$1",
                    job_id,
                )
            finally:
                await pgc.close()
            job = await self._pg.get(job_id)
            # Save message for ack on completion
            self._pending[job_id] = msg
            return job
        finally:
            # Keep channel/connection open would be nicer, but for symmetry close after single get
            await ch.close()
            await conn.close()

    async def list(self, limit: int = 20, status: Optional[str] = None) -> List[Job]:
        if self._pg is None:
            return []
        return await self._pg.list(limit=limit, status=status)

    async def get(self, job_id: int) -> Optional[Job]:
        if self._pg is None:
            return None
        return await self._pg.get(job_id)

    async def complete(self, job_id: int) -> None:
        if self._pg is not None:
            await self._pg.complete(job_id)
        msg = self._pending.pop(job_id, None)
        if msg is not None:
            try:
                await msg.ack()
            except Exception:
                pass

    async def fail(self, job_id: int, error: str) -> None:
        if self._pg is not None:
            await self._pg.fail(job_id, error)
        msg = self._pending.pop(job_id, None)
        if msg is not None:
            try:
                await msg.nack(requeue=False)
            except Exception:
                pass

    async def retry(self, job_id: int) -> bool:
        if self._pg is None:
            return False
        ok = await self._pg.retry(job_id)
        if ok:
            # republish
            conn, ch, _ = await self._channel()
            try:
                body = json.dumps({"job_id": job_id}).encode("utf-8")
                await ch.default_exchange.publish(
                    aio_pika.Message(body=body, content_type="application/json", delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                    routing_key=self.queue,
                )
            finally:
                await ch.close()
                await conn.close()
        return ok

    async def cancel(self, job_id: int) -> bool:
        if self._pg is None:
            return False
        ok = await self._pg.cancel(job_id)
        # Attempt to nack if currently pending in our map
        msg = self._pending.pop(job_id, None)
        if msg is not None:
            try:
                await msg.nack(requeue=False)
            except Exception:
                pass
        return ok

    async def update_progress(self, job_id: int, *, done: int | None = None, total: int | None = None, note: str | None = None) -> None:
        if self._pg is not None:
            await self._pg.update_progress(job_id, done=done, total=total, note=note)
