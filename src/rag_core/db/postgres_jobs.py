from __future__ import annotations

import json
from typing import Any, Dict, Optional, List
import asyncio

from sqlalchemy import Table, Column, Integer, Text, TIMESTAMP, JSON, MetaData, text, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .base import JobRepository, Job
from ..types import Db
from ..orm.session import create_engine_from_db


class PostgresJobRepository(JobRepository):
    def __init__(self, db: Db, table: str = "rag_jobs") -> None:
        self.db = db
        self.table_name = table
        self.engine: Engine = create_engine_from_db(db)
        self.metadata = MetaData()
        self.table = Table(
            self.table_name,
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("type", Text, nullable=False),
            Column("payload", JSONB, nullable=False),
            Column("status", Text, nullable=False, server_default=text("'pending'")),
            Column("attempts", Integer, nullable=False, server_default=text("0")),
            Column("error", Text),
            Column("progress_total", Integer),
            Column("progress_done", Integer),
            Column("progress_note", Text),
            Column("created_at", TIMESTAMP(timezone=True), server_default=text("NOW()")),
            Column("started_at", TIMESTAMP(timezone=True)),
            Column("finished_at", TIMESTAMP(timezone=True)),
            extend_existing=True,
        )

    async def ensure(self) -> None:
        def _ensure():
            self.metadata.create_all(self.engine, tables=[self.table])
            with self.engine.begin() as conn:
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {self.table_name}_status_idx ON {self.table_name}(status)"))

        await asyncio.to_thread(_ensure)

    async def enqueue(self, job_type: str, payload: Dict[str, Any]) -> int:
        await self.ensure()

        def _ins() -> int:
            with self.engine.begin() as conn:
                res = conn.execute(
                    self.table.insert().returning(self.table.c.id),
                    {"type": job_type, "payload": payload, "status": "pending", "attempts": 0},
                )
                return int(res.scalar_one())

        return await asyncio.to_thread(_ins)

    async def fetch_and_start(self) -> Optional[Job]:
        await self.ensure()

        def _fetch() -> Optional[Job]:
            with self.engine.begin() as conn:
                row = conn.execute(
                    text(
                        f"""
                        WITH j AS (
                            SELECT id FROM {self.table_name}
                            WHERE status='pending'
                            ORDER BY id
                            LIMIT 1
                            FOR UPDATE SKIP LOCKED
                        )
                        UPDATE {self.table_name} t
                        SET status='processing', started_at=NOW(), attempts = attempts + 1
                        FROM j
                        WHERE t.id = j.id
                        RETURNING t.id, t.type, t.payload, t.status, t.attempts, t.error, t.created_at, t.started_at, t.finished_at, t.progress_done, t.progress_total, t.progress_note
                        """
                    )
                ).mappings().first()
                if not row:
                    return None
                payload = row["payload"]
                return Job(
                    id=int(row["id"]),
                    type=str(row["type"]),
                    payload=payload if isinstance(payload, dict) else json.loads(payload or "{}"),
                    status=str(row["status"]),
                    attempts=int(row["attempts"] or 0),
                    error=row.get("error"),
                    created_at=row.get("created_at"),
                    started_at=row.get("started_at"),
                    finished_at=row.get("finished_at"),
                    progress_done=row.get("progress_done"),
                    progress_total=row.get("progress_total"),
                    progress_note=row.get("progress_note"),
                )

        return await asyncio.to_thread(_fetch)

    async def list(self, limit: int = 20, status: Optional[str] = None) -> List[Job]:
        await self.ensure()

        def _list() -> List[Job]:
            with self.engine.begin() as conn:
                if status:
                    res = conn.execute(
                        text(f"SELECT * FROM {self.table_name} WHERE status=:s ORDER BY id DESC LIMIT :l"),
                        {"s": status, "l": int(limit)},
                    )
                else:
                    res = conn.execute(text(f"SELECT * FROM {self.table_name} ORDER BY id DESC LIMIT :l"), {"l": int(limit)})
                out: List[Job] = []
                for r in res.mappings():
                    payload = r["payload"]
                    out.append(
                        Job(
                            id=int(r["id"]),
                            type=str(r["type"]),
                            payload=payload if isinstance(payload, dict) else json.loads(payload or "{}"),
                            status=str(r["status"]),
                            attempts=int(r["attempts"] or 0),
                            error=r.get("error"),
                            created_at=r.get("created_at"),
                            started_at=r.get("started_at"),
                            finished_at=r.get("finished_at"),
                            progress_done=r.get("progress_done"),
                            progress_total=r.get("progress_total"),
                            progress_note=r.get("progress_note"),
                        )
                    )
                return out

        return await asyncio.to_thread(_list)

    async def get(self, job_id: int) -> Optional[Job]:
        await self.ensure()

        def _get() -> Optional[Job]:
            with self.engine.begin() as conn:
                r = conn.execute(text(f"SELECT * FROM {self.table_name} WHERE id=:i"), {"i": int(job_id)}).mappings().first()
                if not r:
                    return None
                payload = r["payload"]
                return Job(
                    id=int(r["id"]),
                    type=str(r["type"]),
                    payload=payload if isinstance(payload, dict) else json.loads(payload or "{}"),
                    status=str(r["status"]),
                    attempts=int(r["attempts"] or 0),
                    error=r.get("error"),
                    created_at=r.get("created_at"),
                    started_at=r.get("started_at"),
                    finished_at=r.get("finished_at"),
                    progress_done=r.get("progress_done"),
                    progress_total=r.get("progress_total"),
                    progress_note=r.get("progress_note"),
                )

        return await asyncio.to_thread(_get)

    async def complete(self, job_id: int) -> None:
        def _run():
            with self.engine.begin() as conn:
                conn.execute(text(f"UPDATE {self.table_name} SET status='completed', finished_at=NOW(), error=NULL WHERE id=:i"), {"i": int(job_id)})

        await asyncio.to_thread(_run)

    async def fail(self, job_id: int, error: str) -> None:
        def _run():
            with self.engine.begin() as conn:
                conn.execute(
                    text(f"UPDATE {self.table_name} SET status='failed', finished_at=NOW(), error=:e WHERE id=:i"),
                    {"i": int(job_id), "e": error},
                )

        await asyncio.to_thread(_run)

    async def retry(self, job_id: int) -> bool:
        await self.ensure()

        def _run() -> bool:
            with self.engine.begin() as conn:
                row = conn.execute(
                    text(
                        f"UPDATE {self.table_name} SET status='pending', started_at=NULL, finished_at=NULL, error=NULL WHERE id=:i AND status IN ('failed','canceled') RETURNING id"
                    ),
                    {"i": int(job_id)},
                ).first()
                return row is not None

        return await asyncio.to_thread(_run)

    async def cancel(self, job_id: int) -> bool:
        await self.ensure()

        def _run() -> bool:
            with self.engine.begin() as conn:
                row = conn.execute(
                    text(
                        f"UPDATE {self.table_name} SET status='canceled', finished_at=NOW(), error=COALESCE(error,'canceled') WHERE id=:i AND status IN ('pending','processing') RETURNING id"
                    ),
                    {"i": int(job_id)},
                ).first()
                return row is not None

        return await asyncio.to_thread(_run)

    async def update_progress(self, job_id: int, *, done: int | None = None, total: int | None = None, note: str | None = None) -> None:
        await self.ensure()

        def _run():
            with self.engine.begin() as conn:
                fields = []
                params: Dict[str, Any] = {"i": int(job_id)}
                if done is not None:
                    fields.append("progress_done = :d")
                    params["d"] = int(done)
                if total is not None:
                    fields.append("progress_total = :t")
                    params["t"] = int(total)
                if note is not None:
                    fields.append("progress_note = :n")
                    params["n"] = str(note)
                if not fields:
                    return
                sql = f"UPDATE {self.table_name} SET {', '.join(fields)} WHERE id=:i"
                conn.execute(text(sql), params)

        await asyncio.to_thread(_run)

    async def mark_processing(self, job_id: int) -> None:
        await self.ensure()

        def _run():
            with self.engine.begin() as conn:
                conn.execute(
                    text(f"UPDATE {self.table_name} SET status='processing', started_at=NOW(), attempts = attempts + 1 WHERE id=:i"),
                    {"i": int(job_id)},
                )

        await asyncio.to_thread(_run)
