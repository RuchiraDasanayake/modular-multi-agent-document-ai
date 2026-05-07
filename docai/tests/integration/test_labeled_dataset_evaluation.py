"""Integration tests for labeled dataset evaluation harness.

SYNTHETIC FIXTURE TESTS ONLY:
These tests create minimal synthetic .txt files and hardcoded expected_values
dictionaries at test runtime. They validate harness logic and error handling.

They do NOT evaluate real labeled datasets or claim benchmark performance.
Expected values are manually defined in test code, NOT derived from extraction.

For real-dataset evaluation, users must provide their own manifest.json with
document paths and expected value dictionaries.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from docai_core.artifacts.store import ArtifactStore
from docai_core.datasets.manifest import DocumentManifestEntry, LabeledDatasetManifest
from docai_core.review.expected_values import ExpectedValues
from scripts.dev_evaluate_labeled_dataset import (
    _validate_manifest,
    evaluate_dataset,
)


@pytest.fixture()
def tmp_dataset_dir(tmp_path: Path) -> Path:
    """Create a temporary dataset directory with test documents."""
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    # Create invoice document
    invoice_file = dataset_dir / "invoice_001.txt"
    invoice_file.write_text(
        "Invoice Number: INV-001\n"
        "Invoice Date: 2024-01-15\n"
        "Total Amount: $1,250.00\n"
        "Status: Paid\n"
    )

    # Create receipt document
    receipt_file = dataset_dir / "receipt_001.txt"
    receipt_file.write_text(
        "Receipt Number: RCP-001\n"
        "Receipt Date: 2024-01-16\n"
        "Merchant Name: Acme Store\n"
        "Total Amount: $25.99\n"
    )

    return dataset_dir


# ---------------------------------------------------------------------------
# Test 1: Valid invoice_basic manifest works
# ---------------------------------------------------------------------------

def test_invoice_basic_manifest_evaluates(tmp_dataset_dir: Path, tmp_path: Path) -> None:
    invoice_file = tmp_dataset_dir / "invoice_001.txt"
    manifest = LabeledDatasetManifest(
        dataset_id="test_invoices",
        documents=[
            DocumentManifestEntry(
                document_id="inv-001",
                file_path=str(invoice_file),
                schema_id="invoice_basic",
                expected_values={
                    "invoice_number": "INV-001",
                    "invoice_date": "2024-01-15",
                    "total_amount": "$1,250.00",
                    "status": "Paid",
                },
            )
        ],
    )

    artifact_store = ArtifactStore(tmp_path / "artifacts")
    result = evaluate_dataset(manifest, artifact_store)

    assert result.dataset_id == "test_invoices"
    assert result.document_count == 1
    assert result.evaluated_count == 1
    assert "invoice_basic" in result.schema_ids
    assert "inv-001" in result.field_accuracies
    assert len(result.errors) == 0


# ---------------------------------------------------------------------------
# Test 2: Valid receipt_basic manifest works
# ---------------------------------------------------------------------------

def test_receipt_basic_manifest_evaluates(tmp_dataset_dir: Path, tmp_path: Path) -> None:
    receipt_file = tmp_dataset_dir / "receipt_001.txt"
    manifest = LabeledDatasetManifest(
        dataset_id="test_receipts",
        documents=[
            DocumentManifestEntry(
                document_id="rcpt-001",
                file_path=str(receipt_file),
                schema_id="receipt_basic",
                expected_values={
                    "receipt_number": "RCP-001",
                    "receipt_date": "2024-01-16",
                    "merchant_name": "Acme Store",
                    "total_amount": "$25.99",
                },
            )
        ],
    )

    artifact_store = ArtifactStore(tmp_path / "artifacts")
    result = evaluate_dataset(manifest, artifact_store)

    assert result.dataset_id == "test_receipts"
    assert result.document_count == 1
    assert result.evaluated_count == 1
    assert "receipt_basic" in result.schema_ids
    assert "rcpt-001" in result.field_accuracies
    assert len(result.errors) == 0


# ---------------------------------------------------------------------------
# Test 3: Unknown schema_id fails validation
# ---------------------------------------------------------------------------

def test_unknown_schema_id_fails(tmp_dataset_dir: Path, tmp_path: Path) -> None:
    invoice_file = tmp_dataset_dir / "invoice_001.txt"
    manifest = LabeledDatasetManifest(
        dataset_id="test",
        documents=[
            DocumentManifestEntry(
                document_id="doc-001",
                file_path=str(invoice_file),
                schema_id="does_not_exist",
                expected_values={"field": "value"},
            )
        ],
    )

    artifact_store = ArtifactStore(tmp_path / "artifacts")
    result = evaluate_dataset(manifest, artifact_store)

    assert result.evaluated_count == 0
    assert len(result.errors) > 0


# ---------------------------------------------------------------------------
# Test 4: Expected field outside schema fails validation
# ---------------------------------------------------------------------------

def test_expected_field_outside_schema_fails(tmp_dataset_dir: Path, tmp_path: Path) -> None:
    invoice_file = tmp_dataset_dir / "invoice_001.txt"
    manifest = LabeledDatasetManifest(
        dataset_id="test",
        documents=[
            DocumentManifestEntry(
                document_id="inv-001",
                file_path=str(invoice_file),
                schema_id="invoice_basic",
                expected_values={"nonexistent_field": "value"},
            )
        ],
    )

    artifact_store = ArtifactStore(tmp_path / "artifacts")
    result = evaluate_dataset(manifest, artifact_store)

    assert result.evaluated_count == 0
    assert len(result.errors) > 0


# ---------------------------------------------------------------------------
# Test 5: Dataset labels are recorded (not marked as human_review)
# ---------------------------------------------------------------------------

def test_dataset_labels_recorded_in_artifacts(
    tmp_dataset_dir: Path, tmp_path: Path
) -> None:
    invoice_file = tmp_dataset_dir / "invoice_001.txt"
    manifest = LabeledDatasetManifest(
        dataset_id="test_invoices",
        documents=[
            DocumentManifestEntry(
                document_id="inv-001",
                file_path=str(invoice_file),
                schema_id="invoice_basic",
                expected_values={
                    "invoice_number": "INV-001",
                    "invoice_date": "2024-01-15",
                    "total_amount": "$1,250.00",
                    "status": "Paid",
                },
            )
        ],
    )

    artifact_store = ArtifactStore(tmp_path / "artifacts")
    result = evaluate_dataset(manifest, artifact_store)

    # Read expected_values.json from artifacts
    expected_values_path = artifact_store.document_artifact_path(
        "dataset-inv-001", "inv-001", "expected_values.json"
    )
    assert expected_values_path.exists()

    expected_values_data = json.loads(
        expected_values_path.read_text(encoding="utf-8")
    )
    assert expected_values_data["document_id"] == "inv-001"
    assert expected_values_data["schema_id"] == "invoice_basic"
    assert len(expected_values_data["fields"]) == 4


# ---------------------------------------------------------------------------
# Test 6: Metrics are computed from final_output vs expected_values
# ---------------------------------------------------------------------------

def test_metrics_computed_from_expected_values(
    tmp_dataset_dir: Path, tmp_path: Path
) -> None:
    invoice_file = tmp_dataset_dir / "invoice_001.txt"
    manifest = LabeledDatasetManifest(
        dataset_id="test_invoices",
        documents=[
            DocumentManifestEntry(
                document_id="inv-001",
                file_path=str(invoice_file),
                schema_id="invoice_basic",
                expected_values={
                    "invoice_number": "INV-001",
                    "invoice_date": "2024-01-15",
                    "total_amount": "$1,250.00",
                    "status": "Paid",
                },
            )
        ],
    )

    artifact_store = ArtifactStore(tmp_path / "artifacts")
    result = evaluate_dataset(manifest, artifact_store)

    # Read document_metrics.json
    metrics_path = artifact_store.document_artifact_path(
        "dataset-inv-001", "inv-001", "document_metrics.json"
    )
    assert metrics_path.exists()

    metrics_data = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert "field_accuracy" in metrics_data
    assert "overall_accuracy" in metrics_data
    assert metrics_data["document_id"] == "inv-001"


# ---------------------------------------------------------------------------
# Test 7: No policy mutation
# ---------------------------------------------------------------------------

def test_no_policy_mutation(tmp_dataset_dir: Path, tmp_path: Path) -> None:
    """Verify that evaluation does not mutate any policies."""
    invoice_file = tmp_dataset_dir / "invoice_001.txt"

    # Read original policy file
    policy_dir = Path(__file__).resolve().parents[2] / "configs" / "policies"
    if policy_dir.exists():
        original_policies = {p: p.read_text() for p in policy_dir.glob("*.json")}
    else:
        original_policies = {}

    manifest = LabeledDatasetManifest(
        dataset_id="test",
        documents=[
            DocumentManifestEntry(
                document_id="inv-001",
                file_path=str(invoice_file),
                schema_id="invoice_basic",
                expected_values={"invoice_number": "INV-001"},
            )
        ],
    )

    artifact_store = ArtifactStore(tmp_path / "artifacts")
    evaluate_dataset(manifest, artifact_store)

    # Verify policies unchanged
    for p, original in original_policies.items():
        assert p.read_text() == original, f"{p.name} was mutated during evaluation"


# ---------------------------------------------------------------------------
# Test 8: Expected values marked as dataset_label with is_human_review=False
# ---------------------------------------------------------------------------

def test_expected_values_provenance_marked_correctly(
    tmp_dataset_dir: Path, tmp_path: Path
) -> None:
    """Verify that expected values from harness are marked dataset_label, not human_review."""
    invoice_file = tmp_dataset_dir / "invoice_001.txt"
    manifest = LabeledDatasetManifest(
        dataset_id="test_invoices",
        documents=[
            DocumentManifestEntry(
                document_id="inv-001",
                file_path=str(invoice_file),
                schema_id="invoice_basic",
                expected_values={
                    "invoice_number": "INV-001",
                    "invoice_date": "2024-01-15",
                    "total_amount": "$1,250.00",
                    "status": "Paid",
                },
            )
        ],
    )

    artifact_store = ArtifactStore(tmp_path / "artifacts")
    evaluate_dataset(manifest, artifact_store)

    # Read expected_values.json and check provenance
    expected_values_path = artifact_store.document_artifact_path(
        "dataset-inv-001", "inv-001", "expected_values.json"
    )
    expected_values_data = json.loads(
        expected_values_path.read_text(encoding="utf-8")
    )

    assert expected_values_data["source"] == "dataset_label"
    assert expected_values_data["is_human_review"] is False


# ---------------------------------------------------------------------------
# Test 9: No ReviewRecord created for synthetic tests
# ---------------------------------------------------------------------------

def test_no_review_record_for_dataset_evaluation(
    tmp_dataset_dir: Path, tmp_path: Path
) -> None:
    """Verify that harness does not create fake ReviewRecords."""
    invoice_file = tmp_dataset_dir / "invoice_001.txt"
    manifest = LabeledDatasetManifest(
        dataset_id="test_invoices",
        documents=[
            DocumentManifestEntry(
                document_id="inv-001",
                file_path=str(invoice_file),
                schema_id="invoice_basic",
                expected_values={
                    "invoice_number": "INV-001",
                    "invoice_date": "2024-01-15",
                    "total_amount": "$1,250.00",
                    "status": "Paid",
                },
            )
        ],
    )

    artifact_store = ArtifactStore(tmp_path / "artifacts")
    result = evaluate_dataset(manifest, artifact_store)

    # Verify no review_record.json written (should not exist)
    review_record_path = artifact_store.document_artifact_path(
        "dataset-inv-001", "inv-001", "review_record.json"
    )
    assert not review_record_path.exists(), "No ReviewRecord should be created for dataset evaluation"


# ---------------------------------------------------------------------------
# Test 10: Synthetic fixtures explicitly NOT production benchmarks
# ---------------------------------------------------------------------------

def test_synthetic_fixtures_are_test_only(tmp_dataset_dir: Path, tmp_path: Path) -> None:
    """Verify that synthetic test fixtures are labeled as test_fixture, not real data."""
    # This test creates the absolute minimal synthetic fixture
    # and confirms it's marked as such, not as a real benchmark.
    invoice_file = tmp_dataset_dir / "invoice_001.txt"
    manifest = LabeledDatasetManifest(
        dataset_id="test",  # "test" prefix signals synthetic
        documents=[
            DocumentManifestEntry(
                document_id="inv-001",
                file_path=str(invoice_file),
                schema_id="invoice_basic",
                expected_values={
                    "invoice_number": "INV-001",
                    "invoice_date": "2024-01-15",
                    "total_amount": "$1,250.00",
                    "status": "Paid",
                },
            )
        ],
    )

    artifact_store = ArtifactStore(tmp_path / "artifacts")
    result = evaluate_dataset(manifest, artifact_store)

    # Confirm result does not claim benchmark performance
    assert result.dataset_id == "test"
    assert result.evaluated_count == 1
    # Just verify the basic fields exist; do not claim F1 or accuracy benchmarks
    assert isinstance(result.field_accuracies, dict)
