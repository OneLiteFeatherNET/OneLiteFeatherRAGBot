from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from ..ingestion.base import IngestionSource, IngestItem


@dataclass
class Manifest:
    key: str
    total: int


def build_manifest(source: IngestionSource, *, chunk: bool = False) -> Dict[str, Any]:
    # source already encapsulates chunking if needed; we just serialize items
    items: List[Dict[str, Any]] = []
    count = 0
    for it in source.stream():
        items.append({
            "doc_id": it.doc_id,
            "text": it.text,
            "metadata": it.metadata,
            "checksum": it.checksum,
        })
        count += 1
    return {"count": count, "items": items}


def items_from_manifest(data: Dict[str, Any]) -> Iterable[IngestItem]:
    for it in data.get("items", []):
        yield IngestItem(
            doc_id=it["doc_id"],
            text=it["text"],
            metadata=it.get("metadata", {}),
            checksum=it.get("checksum", ""),
        )

