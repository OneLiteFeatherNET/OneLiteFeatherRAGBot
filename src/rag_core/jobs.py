from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Optional

import asyncpg
from asyncpg.types import Json

from .types import Db


@dataclass
class Job:
    id: int
    type: str
    payload: Dict[str, Any]
    status: str


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
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ
            );
            CREATE INDEX IF NOT EXISTS {self.table}_status_idx ON {self.table}(status);
            """
        )

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
                Json(payload),
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
                        RETURNING t.id, t.type, t.payload, t.status
                        """
                    )
                    if not row:
                        return None
                    return Job(id=row["id"], type=row["type"], payload=row["payload"], status=row["status"])  # type: ignore[index]
            finally:
                await conn.close()

        return asyncio.run(_run())

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
