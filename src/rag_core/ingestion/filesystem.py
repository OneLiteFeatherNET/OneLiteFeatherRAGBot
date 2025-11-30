from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List
import hashlib
import logging

from .base import IngestionSource, IngestItem


DEFAULT_EXTS = [
    ".md",
    ".py",
    ".yml",
    ".yaml",
    ".toml",
    ".json",
    ".txt",
]


@dataclass
class FilesystemSource(IngestionSource):
    repo_root: Path
    repo_url: str
    exts: List[str] | None = None

    def stream(self) -> Iterable[IngestItem]:
        log = logging.getLogger(__name__)
        log.info("Scanning filesystem: root=%s url=%s", self.repo_root, self.repo_url)
        exts = self.exts or DEFAULT_EXTS
        for p in self.repo_root.rglob("*"):
            if not p.is_file():
                continue
            if exts and p.suffix not in exts:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel = str(p.relative_to(self.repo_root))
            meta = {
                "repo": self.repo_url,
                "file_path": rel,
                "source_url": f"{self.repo_url}/blob/main/{rel}",
            }
            doc_id = f"{self.repo_url}@{rel}"
            checksum = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
            yield IngestItem(doc_id=doc_id, text=text, metadata=meta, checksum=checksum)
