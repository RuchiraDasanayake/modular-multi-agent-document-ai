"""Unit tests for FUNSD gold 50 evaluator."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from scripts.evaluate_funsd_gold50 import (
    normalize_text,
    load_manifest,
    load_expected_values,
    load_schema,
    extract_field_values,
    compare_extraction,
)


def test_normalize_text():
    """Test text normalization for comparison."""
    assert normalize_text("Hello World") == "hello world"
    assert normalize_text("  HELLO   WORLD  ") == "hello world"
    assert normalize_text("2 / 26 / 98") == "2 / 26 / 98"
    assert normalize_text(None) == ""
    assert normalize_text("") == ""


def test_extract_field_values():
    """Test extracting all field values from final_output."""
    final_output = {
        "fields": [
            {"field_name": "date", "value": "2/26/98"},
            {"field_name": "date", "value": "B 90"},
            {"field_name": "from", "value": "John Doe"},
            {"field_name": "cc", "value": None},
        ]
    }

    dates = extract_field_values(final_output, "date")
    assert dates == ["2/26/98", "B 90"]

    froms = extract_field_values(final_output, "from")
    assert froms == ["John Doe"]

    ccs = extract_field_values(final_output, "cc")
    assert ccs == [None]

    missing = extract_field_values(final_output, "missing_field")
    assert missing == []


def test_compare_extraction_exact_match():
    """Test exact match comparison."""
    result = compare_extraction(
        document_id="test_doc",
        field_name="date",
        extracted_values=["2/26/98"],
        expected_value="2/26/98",
    )
    assert result.match_type == "exact_match"
    assert result.extracted_value == "2/26/98"
    assert result.expected_value == "2/26/98"


def test_compare_extraction_normalized_match():
    """Test normalized match comparison (trimming and whitespace collapsing)."""
    result = compare_extraction(
        document_id="test_doc",
        field_name="name",
        extracted_values=["  John   Doe  "],
        expected_value="John Doe",
    )
    assert result.match_type == "normalized_match"
    assert result.extracted_value == "  John   Doe  "


def test_compare_extraction_missing():
    """Test missing value detection."""
    result = compare_extraction(
        document_id="test_doc",
        field_name="date",
        extracted_values=[],
        expected_value="2/26/98",
    )
    assert result.match_type == "missing"
    assert result.extracted_value is None


def test_compare_extraction_wrong_value():
    """Test wrong value detection."""
    result = compare_extraction(
        document_id="test_doc",
        field_name="date",
        extracted_values=["1/1/99"],
        expected_value="2/26/98",
    )
    assert result.match_type == "wrong_value"
    assert result.extracted_value == "1/1/99"


def test_load_manifest():
    """Test loading manifest."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        manifest = {
            "dataset": "FUNSD",
            "selection_name": "test_v1",
            "documents": [
                {"doc_id": "doc1", "image_path": "path/to/doc1.png"},
                {"doc_id": "doc2", "image_path": "path/to/doc2.png"},
            ]
        }
        json.dump(manifest, f)
        f.flush()
        manifest_path = Path(f.name)

    try:
        loaded = load_manifest(manifest_path)
        assert loaded["dataset"] == "FUNSD"
        assert len(loaded["documents"]) == 2
        assert loaded["documents"][0]["doc_id"] == "doc1"
    finally:
        manifest_path.unlink()


def test_load_schema():
    """Test loading schema."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        schema = {
            "schema_id": "test_schema_v1",
            "name": "Test Schema",
            "fields": [
                {"id": "field1", "name": "field1", "type": "text"},
                {"id": "field2", "name": "field2", "type": "date"},
            ],
            "tables": []
        }
        json.dump(schema, f)
        f.flush()
        schema_path = Path(f.name)

    try:
        loaded = load_schema(schema_path)
        assert loaded["schema_id"] == "test_schema_v1"
        assert len(loaded["fields"]) == 2
    finally:
        schema_path.unlink()


def test_load_expected_values():
    """Test loading expected values from CSV."""
    import csv

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "document_id", "field_name", "occurrence_index", "expected_value",
                "source"
            ]
        )
        writer.writeheader()
        writer.writerow({
            "document_id": "doc1",
            "field_name": "date",
            "occurrence_index": "1",
            "expected_value": "2/26/98",
            "source": "human_labeled_dataset"
        })
        writer.writerow({
            "document_id": "doc1",
            "field_name": "date",
            "occurrence_index": "2",
            "expected_value": "3/15/99",
            "source": "human_labeled_dataset"
        })
        writer.writerow({
            "document_id": "doc2",
            "field_name": "from",
            "occurrence_index": "1",
            "expected_value": "John Doe",
            "source": "human_labeled_dataset"
        })
        f.flush()
        csv_path = Path(f.name)

    try:
        expected = load_expected_values(csv_path)
        assert ("doc1", "date", 1) in expected
        assert len(expected[("doc1", "date", 1)]) == 1
        assert expected[("doc1", "date", 1)][0]["expected_value"] == "2/26/98"
        assert ("doc1", "date", 2) in expected
        assert ("doc2", "from", 1) in expected
    finally:
        csv_path.unlink()
