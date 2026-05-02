from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import idpo.pipeline.inbox as inbox_module
import idpo.pipeline.orchestrator as orchestrator_module
from idpo.core.config import PipelineConfig
from idpo.core.types import DAEOutput, Document, Page
from idpo.pipeline.orchestrator import Pipeline


def test_process_documents_single_doc_queue_fast_path(tmp_path: Path, monkeypatch) -> None:
    config = PipelineConfig()
    config.queue.enabled = True
    pipeline = Pipeline(config=config, run_dir=str(tmp_path / "run"))
    doc = Document(doc_id="doc-1", source="digital", path="doc.txt", pages=[Page(number=1, text="x")])
    dae = DAEOutput(
        doc_id="doc-1",
        doc_type="text_document",
        vendor_cluster="unknown",
        quality_bin="A",
        complexity_bin="1",
        content_profile="text-heavy",
        quality_score=0.9,
        complexity_score=0.1,
    )

    monkeypatch.setattr(
        pipeline.analysis,
        "run",
        lambda payload, ctx: SimpleNamespace(artifacts={"dae_output": dae, "signal": "analysis-signal"}),
    )

    def fail_if_threadpool_created(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("single-document queue path should not create a thread pool")

    monkeypatch.setattr(orchestrator_module.concurrent.futures, "ThreadPoolExecutor", fail_if_threadpool_created)

    captured: dict[str, object] = {}

    def fake_process_document(document: Document, **kwargs):  # noqa: ANN001
        captured["doc_id"] = document.doc_id
        captured["kwargs"] = kwargs
        return "ok"

    monkeypatch.setattr(pipeline, "process_document", fake_process_document)

    results = pipeline.process_documents([doc])

    assert results == ["ok"]
    assert captured["doc_id"] == "doc-1"
    assert captured["kwargs"] == {"dae_output": dae, "analysis_signal": "analysis-signal"}


def test_process_inbox_builds_run_index_once_per_batch(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("IDPO_DATA_DIR", str(runtime_root))

    doc_a = workspace / "one.txt"
    doc_b = workspace / "two.txt"
    doc_a.write_text("Invoice Number: INV-1\nTotal Amount: 10.00\n", encoding="utf-8")
    doc_b.write_text("Invoice Number: INV-2\nTotal Amount: 20.00\n", encoding="utf-8")

    captured: dict[str, object] = {}

    class FakePipeline:
        def __init__(self, config=None, run_dir=None):  # noqa: ANN001
            captured["run_dir"] = run_dir
            captured["build_index_calls"] = []

        def process_documents(self, docs):  # noqa: ANN001
            return [
                SimpleNamespace(
                    doc_id=doc.doc_id,
                    chunks=[SimpleNamespace(chunk_id=f"{doc.doc_id}-chunk")],
                )
                for doc in docs
            ]

        def build_index(self, results, directory=None):  # noqa: ANN001
            calls = captured.setdefault("build_index_calls", [])
            calls.append({"count": len(results), "directory": directory})
            return None

    monkeypatch.setattr(inbox_module, "Pipeline", FakePipeline)
    monkeypatch.setattr(inbox_module, "write_doc_outputs", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        inbox_module,
        "create_doc_record",
        lambda result, doc_dir, expected_fields, doc: {
            "doc_id": result.doc_id,
            "file_name": Path(doc.path).name,
            "entities": [],
            "structured_fields": {},
        },
    )
    monkeypatch.setattr(inbox_module, "aggregate_reward_metrics", lambda records: {})
    monkeypatch.setattr(inbox_module, "write_decision_chain_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(inbox_module, "write_docs_excel", lambda *args, **kwargs: None)
    monkeypatch.setattr(inbox_module, "write_entities_excel", lambda *args, **kwargs: None)
    monkeypatch.setattr(inbox_module, "write_run_excel", lambda *args, **kwargs: None)
    monkeypatch.setattr(inbox_module, "persist_run_telemetry", lambda *args, **kwargs: {"enabled": False})
    monkeypatch.setattr(inbox_module, "entity_records", lambda records, expected_fields: [])

    result = inbox_module.process_inbox(root=workspace, file_paths=[str(doc_a), str(doc_b)])

    build_index_calls = captured["build_index_calls"]
    assert result["metrics"]["processed_doc_count"] == 2
    assert len(build_index_calls) == 1
    assert build_index_calls[0]["count"] == 2


def test_process_inbox_writes_ahmn_state_snapshot_when_direct_import_is_enabled(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("IDPO_DATA_DIR", str(runtime_root))
    monkeypatch.setenv("IDPO_JOB_ID", "job-123")

    doc_path = workspace / "one.txt"
    doc_path.write_text("Invoice Number: INV-1\nTotal Amount: 10.00\n", encoding="utf-8")

    class DummyDirectAdvisor:
        @staticmethod
        def resolve_scope_key(*, job_id=None, run_id=None):  # noqa: ANN001
            return f"job_{job_id}" if job_id else f"run_{run_id}"

        @staticmethod
        def get_state_snapshot(scope_key=None):  # noqa: ANN001
            return {
                "scope_key": scope_key,
                "call_count": 2,
                "policies": {"default": {"alpha": 2.0, "beta": 1.0, "mean": 0.6667}},
                "state_path": str(runtime_root / "ahmn" / "direct_advisor" / "dummy.json"),
            }

    class FakePipeline:
        def __init__(self, config=None, run_dir=None):  # noqa: ANN001
            self.run_dir = run_dir

        def process_documents(self, docs):  # noqa: ANN001
            return [SimpleNamespace(doc_id=doc.doc_id, chunks=[]) for doc in docs]

    monkeypatch.setattr(inbox_module, "Pipeline", FakePipeline)
    monkeypatch.setattr(inbox_module.importlib, "import_module", lambda name: DummyDirectAdvisor)
    monkeypatch.setattr(inbox_module, "write_doc_outputs", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        inbox_module,
        "create_doc_record",
        lambda result, doc_dir, expected_fields, doc: {
            "doc_id": result.doc_id,
            "file_name": Path(doc.path).name,
            "entities": [],
            "structured_fields": {},
        },
    )
    monkeypatch.setattr(inbox_module, "aggregate_reward_metrics", lambda records: {})
    monkeypatch.setattr(inbox_module, "write_decision_chain_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(inbox_module, "write_docs_excel", lambda *args, **kwargs: None)
    monkeypatch.setattr(inbox_module, "write_entities_excel", lambda *args, **kwargs: None)
    monkeypatch.setattr(inbox_module, "write_run_excel", lambda *args, **kwargs: None)
    monkeypatch.setattr(inbox_module, "persist_run_telemetry", lambda *args, **kwargs: {"enabled": False})
    monkeypatch.setattr(inbox_module, "entity_records", lambda records, expected_fields: [])

    config_path = workspace / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "ahmn": {
                    "enabled": True,
                    "direct_import": "ahmn_core.direct_advisor:get_advice",
                }
            }
        ),
        encoding="utf-8",
    )
    result = inbox_module.process_inbox(root=workspace, file_paths=[str(doc_path)], config_path=str(config_path))

    run_payload = result["run_payload"]
    assert run_payload["ahmn_scope_key"] == "job_job-123"
    state_path = Path(run_payload["ahmn_state_path"])
    assert state_path.exists()
    snapshot = json.loads(state_path.read_text(encoding="utf-8"))
    assert snapshot["scope_key"] == "job_job-123"
