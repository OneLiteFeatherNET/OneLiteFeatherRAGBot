from __future__ import annotations

import asyncio
from typing import Dict, Optional, Tuple, List

from sqlalchemy import Table, Column, String, MetaData, insert, select, delete
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from llama_index.core.storage.kvstore.types import BaseKVStore, DEFAULT_COLLECTION

from .orm.session import create_engine_from_db
from .types import Db


class PostgresKVStore(BaseKVStore):
    """Minimal Postgres-backed KV store for LlamaIndex IndexStore.

    Stores JSON values in a table with columns: collection, key, value (JSONB).
    """

    def __init__(self, db: Db, table_name: str = "llama_kv") -> None:
        self._db = db
        self._engine: Engine = create_engine_from_db(db)
        self._table_name = table_name
        self._md = MetaData()
        self._table = Table(
            table_name,
            self._md,
            Column("collection", String, primary_key=True),
            Column("key", String, primary_key=True),
            Column("value", JSONB),
            schema="public",
        )
        self._ensure()

    def _ensure(self) -> None:
        self._md.create_all(self._engine, tables=[self._table])

    def put(self, key: str, val: dict, collection: str = DEFAULT_COLLECTION) -> None:
        with self._engine.begin() as conn:
            stmt = (
                insert(self._table)
                .values(collection=str(collection), key=str(key), value=val)
                .on_conflict_do_update(
                    index_elements=[self._table.c.collection, self._table.c.key],
                    set_={"value": val},
                )
            )
            conn.execute(stmt)

    async def aput(self, key: str, val: dict, collection: str = DEFAULT_COLLECTION) -> None:
        await asyncio.to_thread(self.put, key, val, collection)

    def get(self, key: str, collection: str = DEFAULT_COLLECTION) -> Optional[dict]:
        with self._engine.begin() as conn:
            stmt = select(self._table.c.value).where(
                (self._table.c.collection == str(collection)) & (self._table.c.key == str(key))
            )
            row = conn.execute(stmt).first()
            return dict(row[0]) if row and row[0] is not None else None

    async def aget(self, key: str, collection: str = DEFAULT_COLLECTION) -> Optional[dict]:
        return await asyncio.to_thread(self.get, key, collection)

    def get_all(self, collection: str = DEFAULT_COLLECTION) -> Dict[str, dict]:
        with self._engine.begin() as conn:
            stmt = select(self._table.c.key, self._table.c.value).where(
                self._table.c.collection == str(collection)
            )
            out: Dict[str, dict] = {}
            for k, v in conn.execute(stmt).all():
                if v is not None:
                    out[str(k)] = dict(v)
            return out

    async def aget_all(self, collection: str = DEFAULT_COLLECTION) -> Dict[str, dict]:
        return await asyncio.to_thread(self.get_all, collection)

    def delete(self, key: str, collection: str = DEFAULT_COLLECTION) -> bool:
        with self._engine.begin() as conn:
            stmt = delete(self._table).where(
                (self._table.c.collection == str(collection)) & (self._table.c.key == str(key))
            )
            res = conn.execute(stmt)
            try:
                return (res.rowcount or 0) > 0
            except Exception:
                return True

    async def adelete(self, key: str, collection: str = DEFAULT_COLLECTION) -> bool:
        return await asyncio.to_thread(self.delete, key, collection)

