from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import hashlib

from .base import IngestionSource, IngestItem
from ..chunking import chunk_text


@dataclass
class ChunkingSource(IngestionSource):
    source: IngestionSource
    chunk_size: int = 2000
    overlap: int = 200

    def stream(self) -> Iterable[IngestItem]:
        for item in self.source.stream():
            chunks = chunk_text(item.text, chunk_size=self.chunk_size, overlap=self.overlap)
            total = len(chunks)
            for idx, ct in chunks:
                cid = f"{item.doc_id}#c{idx}"
                md = dict(item.metadata)
                md.update({
                    "parent_id": item.doc_id,
                    "chunk_index": idx,
                    "chunk_total": total,
                })
                csum = hashlib.sha256(ct.encode("utf-8", errors="ignore")).hexdigest()
                yield IngestItem(doc_id=cid, text=ct, metadata=md, checksum=csum)

