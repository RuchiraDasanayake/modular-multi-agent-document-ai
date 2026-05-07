from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from docai_core.artifacts.store import ArtifactStore


@dataclass
class DemoData:
    name: str
    value: int


@dataclass
class NestedData:
    item: DemoData
    created_at: datetime
    path: Path
    tags: list[str]
    metadata: dict[str, object]


def test_base_dir_is_created(tmp_path: Path) -> None:
    base_dir = tmp_path / "artifacts_root"
    assert not base_dir.exists()
    ArtifactStore(base_dir)
    assert base_dir.exists()


def test_create_job_creates_job_folder(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    created = store.create_job("job-1")
    assert created == tmp_path / "runs" / "job-1"
    assert created.exists()


def test_create_document_creates_document_folder(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    created = store.create_document("job-1", "doc-1")
    assert created == tmp_path / "runs" / "job-1" / "documents" / "doc-1"
    assert created.exists()


def test_job_artifact_path_returns_correct_path(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    path = store.job_artifact_path("job-1", "job_context.json")
    assert path == tmp_path / "runs" / "job-1" / "job_context.json"


def test_document_artifact_path_returns_correct_path(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    path = store.document_artifact_path("job-1", "doc-1", "final_output.json")
    assert path == tmp_path / "runs" / "job-1" / "documents" / "doc-1" / "final_output.json"


def test_write_json_and_read_json_work(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    path = store.job_artifact_path("job-1", "job_context.json")
    payload = {"job_id": "job-1", "status": "queued"}
    store.write_json(path, payload)
    assert store.read_json(path) == payload


def test_write_text_and_read_text_work(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    path = store.job_artifact_path("job-1", "note.txt")
    store.write_text(path, "hello artifact")
    assert store.read_text(path) == "hello artifact"


def test_append_jsonl_appends_multiple_lines(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    path = store.job_artifact_path("job-1", "run_log.jsonl")
    store.append_jsonl(path, {"event": "job_created"})
    store.append_jsonl(path, {"event": "documents_queued"})

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "job_created"
    assert json.loads(lines[1])["event"] == "documents_queued"


def test_nested_parent_folders_are_created_automatically(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    path = store.document_artifact_path("job-1", "doc-1", "validation_report.json")
    store.write_json(path, {"pass_status": True})
    assert path.exists()
    assert path.parent.exists()


def test_dataclass_objects_can_be_written_as_json(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    path = store.job_artifact_path("job-1", "metrics_report.json")
    data = DemoData(name="precision", value=95)
    store.write_json(path, data)
    assert store.read_json(path) == {"name": "precision", "value": 95}


def test_dataclass_with_datetime_can_be_written_and_read(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    path = store.job_artifact_path("job-1", "job_context.json")
    now = datetime.now(timezone.utc)
    payload = {"created_at": now}
    store.write_json(path, payload)
    loaded = store.read_json(path)
    assert loaded["created_at"] == now.isoformat()


def test_nested_dataclass_list_dict_structures_serialize_correctly(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    path = store.job_artifact_path("job-1", "nested.json")
    now = datetime.now(timezone.utc)
    nested = NestedData(
        item=DemoData(name="inner", value=1),
        created_at=now,
        path=Path("runs/job-1/documents/doc-1"),
        tags=["a", "b"],
        metadata={"score": 0.9, "enabled": True},
    )
    store.write_json(path, nested)
    loaded = store.read_json(path)
    assert loaded["item"]["name"] == "inner"
    assert loaded["item"]["value"] == 1
    assert loaded["created_at"] == now.isoformat()
    assert loaded["tags"] == ["a", "b"]
    assert loaded["metadata"]["score"] == 0.9


def test_path_serializes_as_string(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    path = store.job_artifact_path("job-1", "path.json")
    artifact_path = Path("runs/job-1/metrics_report.json")
    payload = {"artifact_path": artifact_path}
    store.write_json(path, payload)
    loaded = store.read_json(path)
    assert loaded["artifact_path"] == str(artifact_path)
