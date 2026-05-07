"""Integration tests: RuntimeOrchestrator with model-centered pipeline.

Uses a fake QwenExtractionStep — no real Qwen/Ollama endpoint required.
Verifies that build_model_pipeline() wires ModelCenteredExtractionRunner
and GroundingValidationRunner through the full runtime stack.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
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
from docai_core.extraction.qwen_extraction_step import QwenExtractionStep
from docai_core.orchestration.pipeline_factory import build_model_pipeline
from docai_core.orchestration.runtime_orchestrator import RuntimeOrchestrator
from docai_core.plugins.models.base import ModelRequest, ModelResponse


# ---------------------------------------------------------------------------
# Fake model plugin
# ---------------------------------------------------------------------------

@dataclass
class _FakePlugin:
    plugin_id: str = "fake"
    provider_name: str = "fake"
    model_name: str = "fake-model"
    response_text: str = "{}"

    def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            text=self.response_text,
            model_name=self.model_name,
            is_stub=False,
            success=True,
        )


def _fake_step(fields: dict[str, tuple[str, float]]) -> QwenExtractionStep:
    """Return a step whose model returns the given {field: (value, confidence)}."""
    entities = [{"key": k, "value": v, "confidence": c} for k, (v, c) in fields.items()]
    payload = json.dumps({"entities": entities})
    return QwenExtractionStep(model_plugin=_FakePlugin(response_text=payload))


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

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


def _write_invoice(tmp_path) -> str:
    fd, path = tempfile.mkstemp(suffix=".txt", dir=tmp_path)
    os.write(fd, _INVOICE_TEXT.encode("utf-8"))
    os.close(fd)
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_run_job_with_model_pipeline_all_job_artifacts_written(tmp_path) -> None:
    txt_path = _write_invoice(tmp_path)
    step = _fake_step({"invoice_number": ("INV-001", 0.92)})
    store = ArtifactStore(tmp_path / "artifacts")
    orchestrator = RuntimeOrchestrator(
        artifact_store=store,
        pipeline_config=build_model_pipeline(model_step=step),
    )
    orchestrator.run_job(
        project=_project(), schema=_schema(), job=_job(),
        documents=[_document(txt_path)],
    )

    for filename in ["job_context.json", "document_queue.json", "extracted_data_export.json"]:
        assert store.job_artifact_path("job-1", filename).exists(), f"missing {filename}"

    for filename in [
        "document_profile.json", "selected_policy.json", "run_plan.json",
        "ocr_output.json", "extracted_output.json", "validation_report.json",
        "recovery_report.json", "final_output.json",
    ]:
        assert store.document_artifact_path("job-1", "doc-1", filename).exists(), f"missing {filename}"


def test_model_pipeline_artifacts_are_not_stub(tmp_path) -> None:
    txt_path = _write_invoice(tmp_path)
    step = _fake_step({})
    store = ArtifactStore(tmp_path / "artifacts")
    RuntimeOrchestrator(
        artifact_store=store,
        pipeline_config=build_model_pipeline(model_step=step),
    ).run_job(project=_project(), schema=_schema(), job=_job(), documents=[_document(txt_path)])

    for artifact_path, label in [
        (store.job_artifact_path("job-1", "job_context.json"), "job_context"),
        (store.job_artifact_path("job-1", "document_queue.json"), "document_queue"),
    ]:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert payload["is_stub"] is False, f"{label} should not be stub"
        assert payload["generated_by"] == "model_centered_pipeline_v1", label


def test_model_pipeline_writes_grounding_validation_report(tmp_path) -> None:
    txt_path = _write_invoice(tmp_path)
    # Model returns value present in source → grounding passes
    step = _fake_step({"invoice_number": ("INV-001", 0.95)})
    store = ArtifactStore(tmp_path / "artifacts")
    RuntimeOrchestrator(
        artifact_store=store,
        pipeline_config=build_model_pipeline(model_step=step),
    ).run_job(project=_project(), schema=_schema(), job=_job(), documents=[_document(txt_path)])

    report = json.loads(
        store.document_artifact_path("job-1", "doc-1", "validation_report.json")
        .read_text(encoding="utf-8")
    )
    assert "pass_status" in report
    assert "summary" in report
    assert report["summary"] != "stub validation passed"


def test_model_pipeline_extraction_method_is_model_or_kv(tmp_path) -> None:
    txt_path = _write_invoice(tmp_path)
    step = _fake_step({"invoice_number": ("INV-001", 0.90), "total_amount": ("$100.00", 0.85)})
    store = ArtifactStore(tmp_path / "artifacts")
    RuntimeOrchestrator(
        artifact_store=store,
        pipeline_config=build_model_pipeline(model_step=step),
    ).run_job(project=_project(), schema=_schema(), job=_job(), documents=[_document(txt_path)])

    extracted = json.loads(
        store.document_artifact_path("job-1", "doc-1", "extracted_output.json")
        .read_text(encoding="utf-8")
    )
    valid_methods = {"model_extraction", "hybrid_kv_model", "generic_kv", "not_found"}
    for field in extracted["fields"]:
        assert field["extraction_method"] in valid_methods, (
            f"{field['field_name']}: unexpected method {field['extraction_method']!r}"
        )
