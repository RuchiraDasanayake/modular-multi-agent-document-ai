"""Tests for load_extraction_schema() and the invoice_basic.json config."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from docai_core.schemas import load_extraction_schema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "configs" / "extraction_schemas"


# ---------------------------------------------------------------------------
# Test 1: invoice_basic loads without error and returns correct shape
# ---------------------------------------------------------------------------

def test_load_invoice_basic_returns_extraction_schema() -> None:
    schema = load_extraction_schema("invoice_basic")
    assert schema.schema_id == "invoice_basic"
    assert schema.version == "v1"
    assert len(schema.fields) == 4


# ---------------------------------------------------------------------------
# Test 2: all four canonical field names are present
# ---------------------------------------------------------------------------

def test_load_invoice_basic_has_expected_field_names() -> None:
    schema = load_extraction_schema("invoice_basic")
    names = {f.name for f in schema.fields}
    assert names == {"invoice_number", "invoice_date", "total_amount", "status"}


# ---------------------------------------------------------------------------
# Test 3: aliases are populated for fields that declare them
# ---------------------------------------------------------------------------

def test_load_invoice_basic_fields_carry_aliases() -> None:
    schema = load_extraction_schema("invoice_basic")
    by_name = {f.name: f for f in schema.fields}
    assert "invoice_no" in by_name["invoice_number"].aliases
    assert "date" in by_name["invoice_date"].aliases
    assert "total" in by_name["total_amount"].aliases


# ---------------------------------------------------------------------------
# Test 4: custom schema_dir is respected
# ---------------------------------------------------------------------------

def test_load_extraction_schema_uses_custom_dir(tmp_path: Path) -> None:
    data = {
        "schema_id": "custom_schema",
        "name": "Custom",
        "version": "v1",
        "project_id": "test",
        "fields": [
            {"field_id": "a", "name": "field_a", "description": "First field", "type": "str"}
        ],
        "tables": [],
    }
    (tmp_path / "custom_schema.json").write_text(json.dumps(data), encoding="utf-8")

    schema = load_extraction_schema("custom_schema", schema_dir=tmp_path)
    assert schema.schema_id == "custom_schema"
    assert schema.fields[0].name == "field_a"


# ---------------------------------------------------------------------------
# Test 5: ValueError raised for unknown schema_id
# ---------------------------------------------------------------------------

def test_load_extraction_schema_raises_for_missing_schema(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not found"):
        load_extraction_schema("nonexistent_schema", schema_dir=tmp_path)
