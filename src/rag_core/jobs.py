from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, List
from datetime import datetime

import asyncpg

from .types import Db


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


class JobStore:
    def __init__(self, db: Db, table: str = "rag_jobs") -> None:
        self.db = db
        self.table = table

    def _dsn(self) -> str:
        return f"postgresql://{self.db.user}:{self.db.password}@{self.db.host}:{self.db.port}/{self.db.database}"

    async def _ensure_table_async(self, conn: asyncpg.Connection) -> None:
        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.table} (
                id BIGSERIAL PRIMARY KEY,
                type TEXT NOT NULL,
                payload JSONB NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INT NOT NULL DEFAULT 0,
                error TEXT,
                progress_total INT,
                progress_done INT,
                progress_note TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ
            );
            CREATE INDEX IF NOT EXISTS {self.table}_status_idx ON {self.table}(status);
            """
        )
        # Ensure new columns exist (for upgrades)
        await conn.execute(f"ALTER TABLE {self.table} ADD COLUMN IF NOT EXISTS progress_total INT")
        await conn.execute(f"ALTER TABLE {self.table} ADD COLUMN IF NOT EXISTS progress_done INT")
        await conn.execute(f"ALTER TABLE {self.table} ADD COLUMN IF NOT EXISTS progress_note TEXT")

    def ensure_table(self) -> None:
        async def _run():
            conn = await asyncpg.connect(self._dsn())
            try:
                await self._ensure_table_async(conn)
            finally:
                await conn.close()

        asyncio.run(_run())

    async def enqueue_async(self, job_type: str, payload: Dict[str, Any]) -> int:
        conn = await asyncpg.connect(self._dsn())
        try:
            await self._ensure_table_async(conn)
            row = await conn.fetchrow(
                f"INSERT INTO {self.table} (type, payload) VALUES ($1, $2) RETURNING id",
                job_type,
                json.dumps(payload),
            )
            return int(row["id"])  # type: ignore[index]
        finally:
            await conn.close()

    def enqueue(self, job_type: str, payload: Dict[str, Any]) -> int:
        """Synchronous wrapper for non-async contexts (e.g., CLI)."""
        async def _run() -> int:
            return await self.enqueue_async(job_type, payload)

        return asyncio.run(_run())

    def fetch_and_start(self) -> Optional[Job]:
        async def _run() -> Optional[Job]:
            conn = await asyncpg.connect(self._dsn())
            try:
                await self._ensure_table_async(conn)
                async with conn.transaction():
                    row = await conn.fetchrow(
                        f"""
                            WITH j AS (
                                SELECT id FROM {self.table}
                                WHERE status='pending'
                                ORDER BY id
                                LIMIT 1
                                FOR UPDATE SKIP LOCKED
                            )
                            UPDATE {self.table} t
                            SET status='processing', started_at=NOW(), attempts = attempts + 1
                            FROM j
                            WHERE t.id = j.id
                            RETURNING t.id, t.type, t.payload, t.status, t.attempts, t.error, t.created_at, t.started_at, t.finished_at, t.progress_done, t.progress_total, t.progress_note
                            """
                    )
                    if not row:
                        return None
                    payload = row["payload"]
                    if isinstance(payload, str):
                        try:
                            payload = json.loads(payload)
                        except Exception:
                            payload = {"_raw": payload}
                    return Job(
                        id=row["id"],
                        type=row["type"],
                        payload=payload,
                        status=row["status"],
                        attempts=row["attempts"],
                        error=row["error"],
                        created_at=row["created_at"],
                        started_at=row["started_at"],
                        finished_at=row["finished_at"],
                    )  # type: ignore[index]
            finally:
                await conn.close()

        return asyncio.run(_run())

    async def list_jobs_async(self, limit: int = 20, status: Optional[str] = None) -> List[Job]:
        conn = await asyncpg.connect(self._dsn())
        try:
            await self._ensure_table_async(conn)
            if status:
                rows = await conn.fetch(
                    f"SELECT id, type, payload, status, attempts, error, created_at, started_at, finished_at FROM {self.table} WHERE status=$1 ORDER BY id DESC LIMIT $2",
                    status,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    f"SELECT id, type, payload, status, attempts, error, created_at, started_at, finished_at FROM {self.table} ORDER BY id DESC LIMIT $1",
                    limit,
                )
            out: List[Job] = []
            for r in rows:
                payload = r["payload"]
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except Exception:
                        payload = {"_raw": payload}
                out.append(
                    Job(
                        id=r["id"],
                        type=r["type"],
                        payload=payload,
                        status=r["status"],
                        attempts=r["attempts"],
                        error=r["error"],
                        created_at=r["created_at"],
                        started_at=r["started_at"],
                        finished_at=r["finished_at"],
                    )
                )
            return out
        finally:
            await conn.close()

    async def get_job_async(self, job_id: int) -> Optional[Job]:
        conn = await asyncpg.connect(self._dsn())
        try:
            await self._ensure_table_async(conn)
            r = await conn.fetchrow(
                f"SELECT id, type, payload, status, attempts, error, created_at, started_at, finished_at, progress_done, progress_total, progress_note FROM {self.table} WHERE id=$1",
                job_id,
            )
            if not r:
                return None
            payload = r["payload"]
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {"_raw": payload}
            return Job(
                id=r["id"],
                type=r["type"],
                payload=payload,
                status=r["status"],
                attempts=r["attempts"],
                error=r["error"],
                created_at=r["created_at"],
                started_at=r["started_at"],
                finished_at=r["finished_at"],
            )
        finally:
            await conn.close()

    def complete(self, job_id: int) -> None:
        async def _run() -> None:
            conn = await asyncpg.connect(self._dsn())
            try:
                await conn.execute(
                    f"UPDATE {self.table} SET status='completed', finished_at=NOW(), error=NULL WHERE id=$1",
                    job_id,
                )
            finally:
                await conn.close()

        asyncio.run(_run())

    def fail(self, job_id: int, error: str) -> None:
        async def _run() -> None:
            conn = await asyncpg.connect(self._dsn())
            try:
                await conn.execute(
                    f"UPDATE {self.table} SET status='failed', finished_at=NOW(), error=$2 WHERE id=$1",
                    job_id,
                    error,
                )
            finally:
                await conn.close()

        asyncio.run(_run())

    async def retry_async(self, job_id: int) -> bool:
        conn = await asyncpg.connect(self._dsn())
        try:
            await self._ensure_table_async(conn)
            row = await conn.fetchrow(
                f"UPDATE {self.table} SET status='pending', started_at=NULL, finished_at=NULL, error=NULL WHERE id=$1 AND status IN ('failed','canceled') RETURNING id",
                job_id,
            )
            return row is not None
        finally:
            await conn.close()

    async def cancel_async(self, job_id: int) -> bool:
        conn = await asyncpg.connect(self._dsn())
        try:
            await self._ensure_table_async(conn)
            row = await conn.fetchrow(
                f"UPDATE {self.table} SET status='canceled', finished_at=NOW(), error=COALESCE(error,'canceled') WHERE id=$1 AND status IN ('pending','processing') RETURNING id",
                job_id,
            )
            return row is not None
        finally:
            await conn.close()

    async def update_progress_async(self, job_id: int, *, done: int | None = None, total: int | None = None, note: str | None = None) -> None:
        conn = await asyncpg.connect(self._dsn())
        try:
            await self._ensure_table_async(conn)
            fields = []
            values = []
            if done is not None:
                idx = len(values) + 1
                fields.append(f"progress_done=${idx}")
                values.append(done)
            if total is not None:
                idx = len(values) + 1
                fields.append(f"progress_total=${idx}")
                values.append(total)
            if note is not None:
                idx = len(values) + 1
                fields.append(f"progress_note=${idx}")
                values.append(note)
            if not fields:
                return
            sql = f"UPDATE {self.table} SET {', '.join(fields)} WHERE id=${len(values)+1}"
            values.append(job_id)
            await conn.execute(sql, *values)
        finally:
            await conn.close()
