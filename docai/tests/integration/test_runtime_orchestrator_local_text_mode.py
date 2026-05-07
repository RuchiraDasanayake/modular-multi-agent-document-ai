"""Integration tests: RuntimeOrchestrator with injected pipeline configs.

Verifies that pipeline_config injection correctly activates local_text mode
without breaking the stub default path.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone

from docai_core.artifacts.store import ArtifactStore
from docai_core.contracts.domain import (
    Document,
    DocumentProfile,
    ExtractionSchema,
    Field,
    Job,
    Project,
)
from docai_core.orchestration.pipeline_factory import (
    build_local_text_pipeline,
    build_stub_pipeline,
)
from docai_core.orchestration.runtime_orchestrator import RuntimeOrchestrator

_INVOICE_TEXT = (
    "Invoice Number: INV-001\n"
    "Invoice Date: 2026-03-15\n"
    "Total Amount: $100.00\n"
    "Status: Paid\n"
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _project() -> Project:
    now = _now()
    return Project(
        project_id="proj-1",
        name="Demo Project",
        description="Demo",
        created_at=now,
        updated_at=now,
    )


def _schema() -> ExtractionSchema:
    return ExtractionSchema(
        schema_id="schema-invoice",
        project_id="proj-1",
        name="Invoice Schema",
        description=None,
        version="v1",
        fields=[
            Field(field_id="f1", name="invoice_number", type="str", description=None),
            Field(field_id="f2", name="invoice_date",   type="str", description=None),
            Field(field_id="f3", name="total_amount",   type="str", description=None),
            Field(field_id="f4", name="status",         type="str", description=None),
        ],
    )


def _job() -> Job:
    return Job(
        job_id="job-1",
        project_id="proj-1",
        schema_id="schema-invoice",
        name="Test Run",
        run_type="training",
        status="queued",
        created_at=_now(),
    )


def _document(file_path: str, doc_id: str = "doc-1") -> Document:
    return Document(
        document_id=doc_id,
        job_id="job-1",
        original_filename=os.path.basename(file_path),
        file_path=file_path,
        status="processing",
        uploaded_at=_now(),
        profile=DocumentProfile(document_id=doc_id),
    )


def test_run_job_with_local_text_pipeline_processes_txt_file(tmp_path) -> None:
    fd, txt_path = tempfile.mkstemp(suffix=".txt", dir=tmp_path)
    os.write(fd, _INVOICE_TEXT.encode("utf-8"))
    os.close(fd)

    store = ArtifactStore(tmp_path / "artifacts")
    orchestrator = RuntimeOrchestrator(
        artifact_store=store,
        pipeline_config=build_local_text_pipeline(),
    )

    summary = orchestrator.run_job(
        project=_project(),
        schema=_schema(),
        job=_job(),
        documents=[_document(txt_path)],
    )

    assert summary["is_stub"] is False
    assert summary["generated_by"] == "local_text_pipeline_v1"
    assert summary["document_count"] == 1
    assert summary["completed_count"] == 1

    final_path = store.document_artifact_path("job-1", "doc-1", "final_output.json")
    assert final_path.exists()
    final = json.loads(final_path.read_text(encoding="utf-8"))

    field_map = {f["field_name"]: f["value"] for f in final["fields"]}
    assert field_map["invoice_number"] == "INV-001"
    assert field_map["total_amount"] == "$100.00"
    assert not any(str(v).startswith("fake_") for v in field_map.values())

    job_context = json.loads(
        store.job_artifact_path("job-1", "job_context.json").read_text(encoding="utf-8")
    )
    assert job_context["is_stub"] is False
    assert job_context["generated_by"] == "local_text_pipeline_v1"


def test_run_job_with_local_text_pipeline_all_job_artifacts_written(tmp_path) -> None:
    fd, txt_path = tempfile.mkstemp(suffix=".txt", dir=tmp_path)
    os.write(fd, _INVOICE_TEXT.encode("utf-8"))
    os.close(fd)

    store = ArtifactStore(tmp_path / "artifacts")
    orchestrator = RuntimeOrchestrator(
        artifact_store=store,
        pipeline_config=build_local_text_pipeline(),
    )
    orchestrator.run_job(
        project=_project(),
        schema=_schema(),
        job=_job(),
        documents=[_document(txt_path)],
    )

    for filename in [
        "job_context.json",
        "document_queue.json",
        "metrics_report.json",
        "extracted_data_export.json",
        "run_log.jsonl",
    ]:
        assert store.job_artifact_path("job-1", filename).exists(), f"missing {filename}"

    for filename in [
        "document_profile.json",
        "selected_policy.json",
        "run_plan.json",
        "ocr_output.json",
        "extracted_output.json",
        "validation_report.json",
        "recovery_report.json",
        "final_output.json",
    ]:
        assert store.document_artifact_path("job-1", "doc-1", filename).exists(), f"missing {filename}"


def test_run_job_with_stub_pipeline_unchanged(tmp_path) -> None:
    store = ArtifactStore(tmp_path)
    orchestrator = RuntimeOrchestrator(
        artifact_store=store,
        pipeline_config=build_stub_pipeline(),
    )

    summary = orchestrator.run_job(
        project=_project(),
        schema=_schema(),
        job=_job(),
        documents=[_document("invoice_001.pdf")],
    )

    assert summary["is_stub"] is True
    assert summary["generated_by"] == "stub_runtime_orchestrator"
    assert summary["document_count"] == 1
    assert summary["completed_count"] == 1

    final_path = store.document_artifact_path("job-1", "doc-1", "final_output.json")
    assert final_path.exists()
    final = json.loads(final_path.read_text(encoding="utf-8"))

    field_map = {f["field_name"]: f["value"] for f in final["fields"]}
    assert all(str(v).startswith("fake_") for v in field_map.values())

    job_context = json.loads(
        store.job_artifact_path("job-1", "job_context.json").read_text(encoding="utf-8")
    )
    assert job_context["is_stub"] is True
    assert job_context["generated_by"] == "stub_runtime_orchestrator"


def test_local_text_mode_artifacts_are_not_stub(tmp_path) -> None:
    fd, txt_path = tempfile.mkstemp(suffix=".txt", dir=tmp_path)
    os.write(fd, _INVOICE_TEXT.encode("utf-8"))
    os.close(fd)

    store = ArtifactStore(tmp_path / "artifacts")
    orchestrator = RuntimeOrchestrator(
        artifact_store=store,
        pipeline_config=build_local_text_pipeline(),
    )
    orchestrator.run_job(
        project=_project(),
        schema=_schema(),
        job=_job(),
        documents=[_document(txt_path)],
    )

    final = json.loads(
        store.document_artifact_path("job-1", "doc-1", "final_output.json").read_text(encoding="utf-8")
    )
    assert final["is_stub"] is False
    assert final["generated_by"] == "local_text_pipeline_v1"

    ocr = json.loads(
        store.document_artifact_path("job-1", "doc-1", "ocr_output.json").read_text(encoding="utf-8")
    )
    assert ocr["is_stub"] is False
    assert ocr["generated_by"] == "local_text_pipeline_v1"

    queue = json.loads(
        store.job_artifact_path("job-1", "document_queue.json").read_text(encoding="utf-8")
    )
    assert queue["is_stub"] is False
    assert queue["generated_by"] == "local_text_pipeline_v1"

    context = json.loads(
        store.job_artifact_path("job-1", "job_context.json").read_text(encoding="utf-8")
    )
    assert context["is_stub"] is False
    assert context["generated_by"] == "local_text_pipeline_v1"


def test_local_text_mode_writes_grounding_validation_report(tmp_path) -> None:
    fd, txt_path = tempfile.mkstemp(suffix=".txt", dir=tmp_path)
    os.write(fd, _INVOICE_TEXT.encode("utf-8"))
    os.close(fd)

    store = ArtifactStore(tmp_path / "artifacts")
    orchestrator = RuntimeOrchestrator(
        artifact_store=store,
        pipeline_config=build_local_text_pipeline(),
    )
    orchestrator.run_job(
        project=_project(),
        schema=_schema(),
        job=_job(),
        documents=[_document(txt_path)],
    )

    validation = json.loads(
        store.document_artifact_path("job-1", "doc-1", "validation_report.json").read_text(encoding="utf-8")
    )
    assert validation["pass_status"] is True
    assert "grounded" in validation["summary"]
    assert validation["summary"] != "stub validation passed"


def test_run_job_default_no_pipeline_config_is_stub(tmp_path) -> None:
    store = ArtifactStore(tmp_path)
    orchestrator = RuntimeOrchestrator(artifact_store=store)

    summary = orchestrator.run_job(
        project=_project(),
        schema=_schema(),
        job=_job(),
        documents=[_document("invoice_001.pdf")],
    )

    assert summary["is_stub"] is True
    assert summary["generated_by"] == "stub_runtime_orchestrator"
