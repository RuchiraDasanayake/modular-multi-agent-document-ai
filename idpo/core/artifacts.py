from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    path: str
    kind: str
    metadata: Dict[str, Any]


class ArtifactStore:
    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.raw_dir = self.root / "raw"
        self.clean_dir = self.root / "clean"
        self.meta_dir = self.root / "meta"
        for directory in (self.raw_dir, self.clean_dir, self.meta_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def _write(self, folder: Path, name: str, content: str, artifact_id: str) -> Path:
        safe_name = name.replace(" ", "_")
        path = folder / f"{artifact_id}_{safe_name}"
        path.write_text(content, encoding="utf-8")
        return path

    def _record(self, artifact_id: str, path: Path, kind: str, metadata: Optional[Dict[str, Any]]) -> ArtifactRecord:
        payload = {
            "artifact_id": artifact_id,
            "path": str(path),
            "kind": kind,
            "metadata": metadata or {},
        }
        (self.meta_dir / f"{artifact_id}.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        return ArtifactRecord(**payload)

    def save_text(self, name: str, content: str, kind: str, raw: bool = False,
                  metadata: Optional[Dict[str, Any]] = None) -> ArtifactRecord:
        folder = self.raw_dir if raw else self.clean_dir
        artifact_id = uuid.uuid4().hex
        path = self._write(folder, name, content, artifact_id)
        return self._record(artifact_id, path, kind, metadata)

    def save_json(self, name: str, data: Any, kind: str, raw: bool = False,
                  metadata: Optional[Dict[str, Any]] = None) -> ArtifactRecord:
        text = json.dumps(data, indent=2, sort_keys=True)
        return self.save_text(name, text, kind, raw=raw, metadata=metadata)

    def register_external(self, path: str, kind: str, metadata: Optional[Dict[str, Any]] = None) -> ArtifactRecord:
        artifact_id = uuid.uuid4().hex
        return self._record(artifact_id, Path(path), kind, metadata)
