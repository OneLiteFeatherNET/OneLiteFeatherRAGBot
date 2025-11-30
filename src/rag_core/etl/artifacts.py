from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


class ArtifactStore:
    def put_manifest(self, data: Dict[str, Any]) -> str:  # returns key
        raise NotImplementedError

    def get_manifest(self, key: str) -> Dict[str, Any]:
        raise NotImplementedError


@dataclass
class LocalArtifactStore(ArtifactStore):
    root: Path

    def _ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def put_manifest(self, data: Dict[str, Any]) -> str:
        self._ensure()
        key = uuid.uuid4().hex
        path = self.root / f"manifest-{key}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return key

    def get_manifest(self, key: str) -> Dict[str, Any]:
        path = self.root / f"manifest-{key}.json"
        return json.loads(path.read_text(encoding="utf-8"))

