from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List

from .base import IngestionSource, Item


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

    def stream(self) -> Iterable[Item]:
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
            yield (text, meta)

