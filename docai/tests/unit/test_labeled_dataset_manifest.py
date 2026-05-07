"""Unit tests for labeled dataset manifest validation.

SYNTHETIC FIXTURE TESTS ONLY:
These tests create synthetic fixture files and validate manifest parsing/validation.
They do NOT test real dataset behavior. For real-dataset evaluation, users provide
their own manifest.json with document paths and expected values.

Expected values in tests are hardcoded dictionaries, not derived from extraction."""

from __future__ import annotations

from pathlib import Path

import pytest

from docai_core.datasets.manifest import DocumentManifestEntry, LabeledDatasetManifest
from scripts.dev_evaluate_labeled_dataset import _validate_manifest


@pytest.fixture()
def temp_files(tmp_path: Path) -> dict[str, Path]:
    """Create temporary test files."""
    invoice_file = tmp_path / "invoice.txt"
    invoice_file.write_text("Invoice Number: INV-100\nTotal Amount: $500.00\n")

    receipt_file = tmp_path / "receipt.txt"
    receipt_file.write_text("Receipt Number: RCP-100\nMerchant: Store\nTotal: $25.99\n")

    return {"invoice": invoice_file, "receipt": receipt_file}


def test_valid_invoice_basic_manifest(temp_files: dict[str, Path]) -> None:
    """Valid manifest with invoice_basic schema passes validation."""
    manifest = LabeledDatasetManifest(
        dataset_id="test_invoices",
        documents=[
            DocumentManifestEntry(
                document_id="inv-001",
                file_path=str(temp_files["invoice"]),
                schema_id="invoice_basic",
                expected_values={
                    "invoice_number": "INV-100",
                    "invoice_date": "2024-01-15",
                    "total_amount": "$500.00",
                    "status": "Paid",
                },
            )
        ],
    )
    errors = _validate_manifest(manifest)
    assert errors == []


def test_valid_receipt_basic_manifest(temp_files: dict[str, Path]) -> None:
    """Valid manifest with receipt_basic schema passes validation."""
    manifest = LabeledDatasetManifest(
        dataset_id="test_receipts",
        documents=[
            DocumentManifestEntry(
                document_id="rcpt-001",
                file_path=str(temp_files["receipt"]),
                schema_id="receipt_basic",
                expected_values={
                    "receipt_number": "RCP-100",
                    "receipt_date": "2024-01-15",
                    "merchant_name": "Acme Store",
                    "total_amount": "$25.99",
                },
            )
        ],
    )
    errors = _validate_manifest(manifest)
    assert errors == []


def test_unknown_schema_id_rejected(temp_files: dict[str, Path]) -> None:
    """Unknown schema_id in manifest is rejected."""
    manifest = LabeledDatasetManifest(
        dataset_id="test",
        documents=[
            DocumentManifestEntry(
                document_id="doc-001",
                file_path=str(temp_files["invoice"]),
                schema_id="does_not_exist",
                expected_values={"some_field": "some_value"},
            )
        ],
    )
    errors = _validate_manifest(manifest)
    assert len(errors) == 1
    assert "not found" in errors[0].lower() or "unknown" in errors[0].lower()


def test_expected_field_outside_schema_rejected(temp_files: dict[str, Path]) -> None:
    """Expected field not in schema is rejected."""
    manifest = LabeledDatasetManifest(
        dataset_id="test",
        documents=[
            DocumentManifestEntry(
                document_id="doc-001",
                file_path=str(temp_files["invoice"]),
                schema_id="invoice_basic",
                expected_values={
                    "invoice_number": "INV-100",
                    "nonexistent_field": "value",
                },
            )
        ],
    )
    errors = _validate_manifest(manifest)
    assert len(errors) == 1
    assert "nonexistent_field" in errors[0]


def test_missing_file_rejected(temp_files: dict[str, Path]) -> None:
    """Missing file path is rejected."""
    manifest = LabeledDatasetManifest(
        dataset_id="test",
        documents=[
            DocumentManifestEntry(
                document_id="doc-001",
                file_path="/nonexistent/path/file.txt",
                schema_id="invoice_basic",
                expected_values={"invoice_number": "INV-100"},
            )
        ],
    )
    errors = _validate_manifest(manifest)
    assert len(errors) == 1
    assert "not found" in errors[0].lower()


def test_multiple_validation_errors_collected(temp_files: dict[str, Path]) -> None:
    """Multiple validation errors are all reported."""
    manifest = LabeledDatasetManifest(
        dataset_id="test",
        documents=[
            DocumentManifestEntry(
                document_id="doc-001",
                file_path="/nonexistent/file.txt",
                schema_id="does_not_exist",
                expected_values={},
            )
        ],
    )
    errors = _validate_manifest(manifest)
    assert len(errors) >= 2
