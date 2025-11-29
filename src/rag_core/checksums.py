from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

import asyncpg

from .types import Db


@dataclass
class ChecksumRecord:
    doc_id: str
    checksum: str


class ChecksumStore:
    def __init__(self, db: Db, table: str = "rag_checksums") -> None:
        self.db = db
        self.table = table

    def _dsn(self) -> str:
        return f"postgresql://{self.db.user}:{self.db.password}@{self.db.host}:{self.db.port}/{self.db.database}"

    async def _ensure_table_async(self, conn: asyncpg.Connection) -> None:
        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.table} (
                doc_id TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
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

    def load_map(self) -> Dict[str, str]:
        async def _run() -> Dict[str, str]:
            conn = await asyncpg.connect(self._dsn())
            try:
                await self._ensure_table_async(conn)
                rows = await conn.fetch(f"SELECT doc_id, checksum FROM {self.table}")
                return {r["doc_id"]: r["checksum"] for r in rows}
            finally:
                await conn.close()

        return asyncio.run(_run())

    def upsert_many(self, records: Iterable[ChecksumRecord]) -> None:
        async def _run():
            conn = await asyncpg.connect(self._dsn())
            try:
                await self._ensure_table_async(conn)
                values = [(r.doc_id, r.checksum) for r in records]
                if not values:
                    return
                await conn.executemany(
                    f"""
                    INSERT INTO {self.table} (doc_id, checksum)
                    VALUES ($1, $2)
                    ON CONFLICT (doc_id) DO UPDATE SET checksum = EXCLUDED.checksum, updated_at = NOW();
                    """,
                    values,
                )
            finally:
                await conn.close()

        asyncio.run(_run())

