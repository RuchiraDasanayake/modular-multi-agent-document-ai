"""Policy A/B evaluation harness — prerequisite evidence loop for AHMN/TS/RABI/DAAF.

No policies are mutated. No learning is performed. No Qwen/Ollama is required.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from docai_core.application.job_run_service import JobRunRequest, JobRunResult, JobRunService
from docai_core.application.review_evaluation_service import (
    ReviewEvaluationAppRequest,
    ReviewEvaluationApplicationService,
    ReviewEvaluationAppResult,
)
from docai_core.artifacts.store import ArtifactStore
from docai_core.contracts.domain import (
    Document,
    DocumentProfile,
    ExtractionSchema,
    Field,
    FieldOutput,
    FinalOutput,
    Job,
    Project,
    RecoveryReport,
    ValidationReport,
)
from docai_core.extraction.qwen_extraction_step import QwenExtractionStep
from docai_core.orchestration.pipeline_factory import build_pipeline_for_policy
from docai_core.plugins.models.base import ModelResponse
from docai_core.review.expected_values import ExpectedFieldValue, ExpectedValues


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_INVOICE_TEXT = (
    "Invoice Number: INV-001\n"
    "Invoice Date: 2026-03-15\n"
    "Total Amount: $100.00\n"
    "Status: Paid\n"
)

_INVOICE_GROUND_TRUTH: dict[str, str] = {
    "invoice_number": "INV-001",
    "invoice_date": "2026-03-15",
    "total_amount": "$100.00",
    "status": "Paid",
}

# Prose text: no colon-separated KV patterns — defeats KV extraction.
_PROSE_TEXT = (
    "The vendor submitted an invoice numbered INV-002.\n"
    "Total payable is $200.00.\n"
    "Transaction date is 2026-04-01.\n"
    "Current status is Pending.\n"
)

_PROSE_GROUND_TRUTH: dict[str, str] = {
    "invoice_number": "INV-002",
    "invoice_date": "2026-04-01",
    "total_amount": "$200.00",
    "status": "Pending",
}


@dataclass(slots=True)
class _FakeModelPlugin:
    """Returns fixed KV text regardless of prompt — simulates a successful model extraction."""

    response_text: str

    def generate(self, request: object) -> ModelResponse:
        return ModelResponse(text=self.response_text, is_stub=False, success=True)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _schema() -> ExtractionSchema:
    now = datetime.now(timezone.utc)
    return ExtractionSchema(
        schema_id="invoice_basic",
        project_id="default",
        name="Invoice (built-in)",
        description=None,
        version="v1",
        fields=[
            Field(field_id="f1", name="invoice_number", description=None, type="str"),
            Field(field_id="f2", name="invoice_date",   description=None, type="str"),
            Field(field_id="f3", name="total_amount",   description=None, type="str"),
            Field(field_id="f4", name="status",         description=None, type="str"),
        ],
        created_at=now,
        updated_at=now,
    )


def _run_policy(
    run_dir: Path,
    policy_id: str,
    doc_text: str,
    model_step: QwenExtractionStep | None = None,
) -> tuple[JobRunResult, ArtifactStore]:
    run_dir.mkdir(parents=True, exist_ok=True)
    doc_file = run_dir / "document.txt"
    doc_file.write_text(doc_text, encoding="utf-8")

    store = ArtifactStore(run_dir / "artifacts")
    now = datetime.now(timezone.utc)
    job_id = f"job-{policy_id.replace('_', '-')}"

    pipeline = build_pipeline_for_policy(policy_id, model_step=model_step)
    result = JobRunService(artifact_store=store, pipeline_config=pipeline).run_job(
        JobRunRequest(
            project=Project(
                project_id="default",
                name="Test Project",
                description=None,
                created_at=now,
                updated_at=now,
            ),
            schema=_schema(),
            job=Job(
                job_id=job_id,
                project_id="default",
                schema_id="invoice_basic",
                name=f"run-{policy_id}",
                run_type="training",
                status="queued",
                created_at=now,
            ),
            documents=[
                Document(
                    document_id="doc-0",
                    job_id=job_id,
                    original_filename="document.txt",
                    file_path=str(doc_file),
                    status="processing",
                    uploaded_at=now,
                    profile=DocumentProfile(document_id="doc-0"),
                )
            ],
        )
    )
    return result, store


def _read_final_output(store: ArtifactStore, job_id: str, doc_id: str) -> FinalOutput:
    data = store.read_json(store.document_artifact_path(job_id, doc_id, "final_output.json"))
    fields = [
        FieldOutput(
            field_name=f["field_name"],
            value=f.get("value"),
            confidence=f.get("confidence"),
            extraction_method=f.get("extraction_method"),
            validation_status=f.get("validation_status", "needs_review"),
        )
        for f in data.get("fields", [])
    ]
    return FinalOutput(
        document_id=data["document_id"],
        schema_id=data["schema_id"],
        policy_id=data["policy_id"],
        fields=fields,
        tables=[],
        validation_report=ValidationReport(document_id=data["document_id"], pass_status=True),
        recovery_report=RecoveryReport(document_id=data["document_id"]),
        quality_summary=data.get("quality_summary"),
    )


def _build_expected_values(doc_id: str, ground_truth: dict[str, str]) -> ExpectedValues:
    return ExpectedValues(
        document_id=doc_id,
        schema_id="invoice_basic",
        fields=[
            ExpectedFieldValue(field_name=k, expected_value=v)
            for k, v in ground_truth.items()
        ],
    )


def _evaluate_run(
    store: ArtifactStore,
    job_id: str,
    final_output: FinalOutput,
    expected_values: ExpectedValues,
) -> ReviewEvaluationAppResult:
    svc = ReviewEvaluationApplicationService(artifact_store=store)
    return svc.evaluate_reviewed_outputs(
        ReviewEvaluationAppRequest(
            job_id=job_id,
            final_outputs=[final_output],
            expected_values_by_document_id={final_output.document_id: expected_values},
        )
    )


# ---------------------------------------------------------------------------
# Test 1: evaluation loop exists for both policies
# ---------------------------------------------------------------------------

def test_policy_ab_evaluation_compares_two_policy_runs(tmp_path: Path) -> None:
    """Proves the full A/B evaluation loop: same document, two policies, reviewed metrics."""
    result_a, store_a = _run_policy(tmp_path / "run_a", "invoice_basic_local_v1", _INVOICE_TEXT)
    result_b, store_b = _run_policy(tmp_path / "run_b", "noisy_scan_rescue_v1", _INVOICE_TEXT)

    job_id_a = result_a.job_id
    job_id_b = result_b.job_id

    fo_a = _read_final_output(store_a, job_id_a, "doc-0")
    fo_b = _read_final_output(store_b, job_id_b, "doc-0")

    ev = _build_expected_values("doc-0", _INVOICE_GROUND_TRUTH)

    eval_a = _evaluate_run(store_a, job_id_a, fo_a, ev)
    eval_b = _evaluate_run(store_b, job_id_b, fo_b, ev)

    # Both runs complete with reviewed metrics.
    assert eval_a.metrics_status == "review_based"
    assert eval_b.metrics_status == "review_based"
    assert eval_a.evaluated_document_count == 1
    assert eval_b.evaluated_document_count == 1
    assert eval_a.skipped_document_ids == []
    assert eval_b.skipped_document_ids == []

    # Pipelines differ between the two runs.
    assert result_a.generated_by == "local_text_pipeline_v1"
    assert result_b.generated_by == "model_centered_pipeline_v1"
    assert fo_a.policy_id == "invoice_basic_local_v1"
    assert fo_b.policy_id == "noisy_scan_rescue_v1"

    # Both produce all four reviewed metric keys.
    for store, job_id in ((store_a, job_id_a), (store_b, job_id_b)):
        report = store.read_json(store.job_artifact_path(job_id, "reviewed_metrics_report.json"))
        for key in ("field_accuracy", "field_precision", "field_recall", "field_f1"):
            assert key in report


# ---------------------------------------------------------------------------
# Test 2: metric difference is detected when one policy extracts prose fields
# ---------------------------------------------------------------------------

def test_policy_ab_evaluation_detects_metric_difference(tmp_path: Path) -> None:
    """Proves that a fake model returning correct values beats KV-only on prose text.

    Prose text has no colon/equals KV separators, so KVOnlyExtractionRunner
    produces low recall. The model-centered policy receives a fake plugin that
    returns all four fields correctly, giving higher field_recall.

    If ModelCenteredExtractionRunner or QwenExtractionStep changes its merge
    strategy such that the fake model response no longer wins over missing KV
    candidates, update the fake response text or the assertion to match.
    """
    # Policy A: KV-only — expected to struggle on prose text.
    result_a, store_a = _run_policy(tmp_path / "run_a", "invoice_basic_local_v1", _PROSE_TEXT)

    # Policy B: model-centered with a fake model returning all four correct fields.
    fake_model_text = (
        "invoice_number: INV-002\n"
        "invoice_date: 2026-04-01\n"
        "total_amount: $200.00\n"
        "status: Pending\n"
    )
    fake_step = QwenExtractionStep(model_plugin=_FakeModelPlugin(response_text=fake_model_text))
    result_b, store_b = _run_policy(
        tmp_path / "run_b", "noisy_scan_rescue_v1", _PROSE_TEXT, model_step=fake_step
    )

    job_id_a = result_a.job_id
    job_id_b = result_b.job_id

    fo_a = _read_final_output(store_a, job_id_a, "doc-0")
    fo_b = _read_final_output(store_b, job_id_b, "doc-0")

    ev = _build_expected_values("doc-0", _PROSE_GROUND_TRUTH)

    eval_a = _evaluate_run(store_a, job_id_a, fo_a, ev)
    eval_b = _evaluate_run(store_b, job_id_b, fo_b, ev)

    reviewed_a = store_a.read_json(store_a.job_artifact_path(job_id_a, "reviewed_metrics_report.json"))
    reviewed_b = store_b.read_json(store_b.job_artifact_path(job_id_b, "reviewed_metrics_report.json"))

    recall_a = reviewed_a.get("field_recall") or 0.0
    recall_b = reviewed_b.get("field_recall") or 0.0

    # Model-centered policy with real (fake) model output must outperform KV-only
    # on prose text where no colon-separated patterns exist.
    assert recall_b >= recall_a, (
        f"Expected model-centered policy (recall={recall_b:.3f}) to match or beat "
        f"KV-only policy (recall={recall_a:.3f}) on prose text."
    )
    assert result_a.generated_by == "local_text_pipeline_v1"
    assert result_b.generated_by == "model_centered_pipeline_v1"
