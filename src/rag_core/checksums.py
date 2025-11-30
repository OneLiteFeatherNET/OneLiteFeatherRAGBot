from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, Iterable
import logging

from sqlalchemy import select
from .types import Db
from .orm.session import create_engine_from_db, session_scope
from .orm.models import RagChecksum, Base


@dataclass
class ChecksumRecord:
    doc_id: str
    checksum: str


class ChecksumStore:
    def __init__(self, db: Db, table: str = "rag_checksums") -> None:
        self.db = db
        self.table = table
        self._log = logging.getLogger(__name__)

    def ensure_table(self) -> None:
        # Use ORM metadata to create table if missing
        eng = create_engine_from_db(self.db)
        Base.metadata.create_all(eng, tables=[RagChecksum.__table__])

    def load_map(self) -> Dict[str, str]:
        self.ensure_table()
        with session_scope(self.db) as sess:
            rows = sess.execute(select(RagChecksum.doc_id, RagChecksum.checksum)).all()
            m = {str(doc_id): str(checksum) for (doc_id, checksum) in rows}
            self._log.debug("Loaded checksum map entries: %d", len(m))
            return m

    def upsert_many(self, records: Iterable[ChecksumRecord]) -> None:
        self.ensure_table()
        with session_scope(self.db) as sess:
            for rec in records:
                # merge provides upsert semantics on PK
                sess.merge(RagChecksum(doc_id=rec.doc_id, checksum=rec.checksum))
