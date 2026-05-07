from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any


class ArtifactStore:
    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def job_dir(self, job_id: str) -> Path:
        return self.base_dir / "runs" / job_id

    def document_dir(self, job_id: str, document_id: str) -> Path:
        return self.job_dir(job_id) / "documents" / document_id

    def create_job(self, job_id: str) -> Path:
        path = self.job_dir(job_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def create_document(self, job_id: str, document_id: str) -> Path:
        path = self.document_dir(job_id, document_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def job_artifact_path(self, job_id: str, filename: str) -> Path:
        return self.job_dir(job_id) / filename

    def document_artifact_path(self, job_id: str, document_id: str, filename: str) -> Path:
        return self.document_dir(job_id, document_id) / filename

    def write_json(self, path: str | Path, data: Any) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        normalized = self._serialize(data)
        with target.open("w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2, ensure_ascii=False)
            f.write("\n")
        return target

    def read_json(self, path: str | Path) -> dict:
        source = Path(path)
        with source.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise TypeError("read_json expected a JSON object at root")
        return data

    def write_text(self, path: str | Path, text: str) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def read_text(self, path: str | Path) -> str:
        return Path(path).read_text(encoding="utf-8")

    def append_jsonl(self, path: str | Path, data: Any) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        normalized = self._serialize(data)
        with target.open("a", encoding="utf-8") as f:
            f.write(json.dumps(normalized, ensure_ascii=False))
            f.write("\n")
        return target

    @staticmethod
    def _serialize(data: Any) -> Any:
        if hasattr(data, "to_dict") and callable(data.to_dict):
            return ArtifactStore._serialize(data.to_dict())
        if is_dataclass(data):
            return ArtifactStore._serialize(asdict(data))
        if isinstance(data, datetime):
            return data.isoformat()
        if isinstance(data, Path):
            return str(data)
        if isinstance(data, dict):
            return {k: ArtifactStore._serialize(v) for k, v in data.items()}
        if isinstance(data, list):
            return [ArtifactStore._serialize(v) for v in data]
        return data
