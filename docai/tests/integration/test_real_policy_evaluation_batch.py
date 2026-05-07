"""Real policy evaluation batch harness.

Runs 3 invoice documents through two policies, collects reviewed metrics,
aggregates PolicyPerformanceRecord, and calls AHMNAdvisoryService.

No policies are mutated. No Qwen/Ollama/Tesseract required.
No fake performance records — all metrics derive from real artifact reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from docai_core.application.ahmn_advisory_service import AHMNAdvisoryRequest, AHMNAdvisoryService
from docai_core.application.job_run_service import JobRunRequest, JobRunService
from docai_core.application.review_evaluation_service import (
    ReviewEvaluationAppRequest,
    ReviewEvaluationApplicationService,
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
from docai_core.metrics.evaluator import DocumentMetrics
from docai_core.metrics.policy_performance import DocumentPolicyProfile, PolicyPerformanceAggregator
from docai_core.orchestration.pipeline_factory import build_pipeline_for_policy
from docai_core.plugins.models.base import ModelResponse
from docai_core.review.expected_values import ExpectedFieldValue, ExpectedValues

# ---------------------------------------------------------------------------
# Batch documents
# ---------------------------------------------------------------------------

# Doc 0: clean KV invoice — KV extraction succeeds on all fields.
_DOC0 = (
    "doc-0",
    "Invoice Number: INV-100\nInvoice Date: 2026-01-10\nTotal Amount: $500.00\nStatus: Paid\n",
    {"invoice_number": "INV-100", "invoice_date": "2026-01-10",
     "total_amount": "$500.00", "status": "Paid"},
    None,
)

# Doc 1: prose — KV misses fields; fake model returns all four for model-centered policy.
_DOC1 = (
    "doc-1",
    ("The vendor submitted invoice INV-101.\n"
     "The total amount due is $750.00.\n"
     "Transaction date is 2026-02-20.\n"
     "Current status is Pending.\n"),
    {"invoice_number": "INV-101", "invoice_date": "2026-02-20",
     "total_amount": "$750.00", "status": "Pending"},
    "invoice_number: INV-101\ninvoice_date: 2026-02-20\ntotal_amount: $750.00\nstatus: Pending\n",
)

# Doc 2: KV invoice with status field absent from source.
_DOC2 = (
    "doc-2",
    "Invoice Number: INV-102\nInvoice Date: 2026-03-05\nTotal Amount: $300.00\n",
    {"invoice_number": "INV-102", "invoice_date": "2026-03-05",
     "total_amount": "$300.00", "status": "Overdue"},
    None,
)

_BATCH = [_DOC0, _DOC1, _DOC2]
_POLICIES = ("invoice_basic_local_v1", "noisy_scan_rescue_v1")


# ---------------------------------------------------------------------------
# Fake model plugin
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class _FakeModelPlugin:
    response_text: str

    def generate(self, request: object) -> ModelResponse:
        return ModelResponse(text=self.response_text, is_stub=False, success=True)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _schema() -> ExtractionSchema:
    now = datetime.now(timezone.utc)
    return ExtractionSchema(
        schema_id="invoice_basic", project_id="default", name="Invoice (built-in)",
        description=None, version="v1",
        fields=[
            Field(field_id="f1", name="invoice_number", description=None, type="str"),
            Field(field_id="f2", name="invoice_date",   description=None, type="str"),
            Field(field_id="f3", name="total_amount",   description=None, type="str"),
            Field(field_id="f4", name="status",         description=None, type="str"),
        ],
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )


def _run_one(
    run_dir: Path, policy_id: str, doc_id: str, doc_text: str, model_text: str | None
) -> tuple[str, ArtifactStore]:
    run_dir.mkdir(parents=True, exist_ok=True)
    doc_file = run_dir / f"{doc_id}.txt"
    doc_file.write_text(doc_text, encoding="utf-8")
    store = ArtifactStore(run_dir / "artifacts")
    now = datetime.now(timezone.utc)
    job_id = f"job-{policy_id.replace('_', '-')}-{doc_id}"
    model_step = (
        QwenExtractionStep(model_plugin=_FakeModelPlugin(response_text=model_text))
        if model_text else None
    )
    pipeline = build_pipeline_for_policy(policy_id, model_step=model_step)
    JobRunService(artifact_store=store, pipeline_config=pipeline).run_job(
        JobRunRequest(
            project=Project(project_id="default", name="Batch Test", description=None,
                            created_at=now, updated_at=now),
            schema=_schema(),
            job=Job(job_id=job_id, project_id="default", schema_id="invoice_basic",
                    name=f"batch-{policy_id}-{doc_id}", run_type="training",
                    status="queued", created_at=now),
            documents=[Document(
                document_id=doc_id, job_id=job_id, original_filename=f"{doc_id}.txt",
                file_path=str(doc_file), status="processing", uploaded_at=now,
                profile=DocumentProfile(document_id=doc_id),
            )],
        )
    )
    return job_id, store


def _read_final_output(store: ArtifactStore, job_id: str, doc_id: str) -> FinalOutput:
    data = store.read_json(store.document_artifact_path(job_id, doc_id, "final_output.json"))
    return FinalOutput(
        document_id=data["document_id"], schema_id=data["schema_id"],
        policy_id=data["policy_id"],
        fields=[
            FieldOutput(
                field_name=f["field_name"], value=f.get("value"),
                confidence=f.get("confidence"), extraction_method=f.get("extraction_method"),
                validation_status=f.get("validation_status", "needs_review"),
            )
            for f in data.get("fields", [])
        ],
        tables=[],
        validation_report=ValidationReport(document_id=data["document_id"], pass_status=True),
        recovery_report=RecoveryReport(document_id=data["document_id"]),
        quality_summary=data.get("quality_summary"),
    )


def _dm_from_dict(d: dict, doc_id: str | None = None) -> DocumentMetrics:
    return DocumentMetrics(
        document_id=doc_id or d["document_id"],
        schema_id=d["schema_id"],
        field_total=d["field_total"], field_correct=d["field_correct"],
        field_accuracy=d.get("field_accuracy"),
        table_cell_total=d.get("table_cell_total", 0),
        table_cell_correct=d.get("table_cell_correct", 0),
        table_cell_accuracy=d.get("table_cell_accuracy"),
        overall_accuracy=d.get("overall_accuracy"),
        corrected_field_count=d.get("corrected_field_count", 0),
        corrected_table_row_count=d.get("corrected_table_row_count", 0),
        missing_expected_field_count=d.get("missing_expected_field_count", 0),
        extra_extracted_field_count=d.get("extra_extracted_field_count", 0),
        field_true_positive=d.get("field_true_positive", 0),
        field_false_positive=d.get("field_false_positive", 0),
        field_false_negative=d.get("field_false_negative", 0),
        field_precision=d.get("field_precision"), field_recall=d.get("field_recall"),
        field_f1=d.get("field_f1"),
    )


def _evaluate_policy_batch(
    tmp_root: Path, policy_id: str, document_type: str = "invoice", quality_bin: str = "mixed",
) -> tuple[list[DocumentMetrics], dict[str, DocumentPolicyProfile]]:
    """Run all 3 batch documents under a policy; return (metrics, keyed profile_map)."""
    metrics: list[DocumentMetrics] = []
    profiles: dict[str, DocumentPolicyProfile] = {}

    for doc_id, doc_text, ground_truth, fake_model_text in _BATCH:
        effective = fake_model_text if "noisy" in policy_id else None
        job_id, store = _run_one(tmp_root / doc_id, policy_id, doc_id, doc_text, effective)

        fo = _read_final_output(store, job_id, doc_id)
        ev = ExpectedValues(
            document_id=doc_id, schema_id="invoice_basic",
            fields=[ExpectedFieldValue(field_name=k, expected_value=v)
                    for k, v in ground_truth.items()],
        )
        eval_r = ReviewEvaluationApplicationService(artifact_store=store).evaluate_reviewed_outputs(
            ReviewEvaluationAppRequest(
                job_id=job_id, final_outputs=[fo],
                expected_values_by_document_id={doc_id: ev},
            )
        )
        assert eval_r.metrics_status == "review_based"

        dm_data = store.read_json(store.document_artifact_path(job_id, doc_id, "document_metrics.json"))
        keyed_id = f"{policy_id}-{doc_id}"
        metrics.append(_dm_from_dict(dm_data, doc_id=keyed_id))
        profiles[keyed_id] = DocumentPolicyProfile(
            policy_id=policy_id, policy_version="v1",
            document_type=document_type, quality_bin=quality_bin,
        )

    return metrics, profiles


def _collect_both_policies(tmp_root: Path):
    all_metrics: list[DocumentMetrics] = []
    all_profiles: dict[str, DocumentPolicyProfile] = {}
    for policy_id in _POLICIES:
        m, p = _evaluate_policy_batch(tmp_root / policy_id, policy_id)
        all_metrics.extend(m)
        all_profiles.update(p)
    return all_metrics, all_profiles


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_batch_produces_artifacts_for_both_policies(tmp_path: Path) -> None:
    """Both policies produce final_output.json and correct selected_policy.json per document."""
    for policy_id in _POLICIES:
        for doc_id, doc_text, _, fake_model_text in _BATCH:
            effective = fake_model_text if "noisy" in policy_id else None
            job_id, store = _run_one(tmp_path / policy_id / doc_id, policy_id, doc_id,
                                     doc_text, effective)
            fo_path = store.document_artifact_path(job_id, doc_id, "final_output.json")
            sp_path = store.document_artifact_path(job_id, doc_id, "selected_policy.json")
            assert fo_path.exists(), f"final_output.json missing for {policy_id}/{doc_id}"
            assert sp_path.exists(), f"selected_policy.json missing for {policy_id}/{doc_id}"
            assert store.read_json(sp_path)["policy_id"] == policy_id


def test_batch_metrics_are_review_based(tmp_path: Path) -> None:
    """ReviewEvaluationApplicationService marks all runs as review_based; field_total=4."""
    for policy_id in _POLICIES:
        metrics, _ = _evaluate_policy_batch(tmp_path / policy_id, policy_id)
        assert len(metrics) == 3
        for dm in metrics:
            assert dm.field_total == 4


def test_policy_performance_records_grouped_by_policy(tmp_path: Path) -> None:
    """PolicyPerformanceAggregator produces one record per policy, document_count=3 each."""
    all_metrics, all_profiles = _collect_both_policies(tmp_path)
    records = PolicyPerformanceAggregator().aggregate(all_metrics, all_profiles)

    assert len(records) == 2
    by_policy = {r.policy_id: r for r in records}
    assert set(by_policy) == set(_POLICIES)
    for policy_id in _POLICIES:
        assert by_policy[policy_id].document_count == 3


def test_ahmn_advisory_service_recommends_from_real_evidence(tmp_path: Path) -> None:
    """AHMNAdvisoryService recommends from real aggregated evidence — read-only, no mutations."""
    all_metrics, all_profiles = _collect_both_policies(tmp_path)
    records = PolicyPerformanceAggregator().aggregate(all_metrics, all_profiles)
    assert len(records) == 2

    result = AHMNAdvisoryService().recommend(
        AHMNAdvisoryRequest(
            records=records, document_type="invoice", quality_bin="mixed",
            min_document_count=3,   # matches fixture batch size
        )
    )

    assert result.status == "recommended"
    assert result.recommendation is not None
    assert result.recommendation.policy_id in _POLICIES
    assert result.recommendation.evidence_document_count == 3
    assert result.recommendation.score is not None
    assert 0.0 <= result.recommendation.score <= 1.0
    assert (result.recommendation.field_f1 is not None
            or result.recommendation.field_accuracy is not None)


def test_no_policy_files_mutated(tmp_path: Path) -> None:
    """Policy JSON files are byte-identical after running the batch."""
    policy_dir = Path(__file__).resolve().parents[2] / "configs" / "policies"
    snapshots = {p: p.read_text(encoding="utf-8") for p in policy_dir.glob("*.json")}

    for policy_id in _POLICIES:
        _evaluate_policy_batch(tmp_path / policy_id, policy_id)

    for p, original in snapshots.items():
        assert p.read_text(encoding="utf-8") == original, f"{p.name} was mutated"
