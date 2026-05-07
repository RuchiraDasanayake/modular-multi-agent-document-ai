from datetime import datetime, timezone
from pathlib import Path

import pytest

from docai_core.contracts.domain import Column, ExtractionSchema, Field, Table
from docai_core.schemas.registry import SchemaRegistry


def _build_schema(
    *,
    schema_id: str = "sample_v1",
    field_names: list[str] | None = None,
    table_names: list[str] | None = None,
    column_names: list[str] | None = None,
    field_description: str | None = "Field description",
    column_description: str | None = "Column description",
) -> ExtractionSchema:
    if field_names is None:
        field_names = ["invoice_id", "total_amount"]
    if table_names is None:
        table_names = ["line_items"]
    if column_names is None:
        column_names = ["description", "line_total"]

    fields = [
        Field(
            field_id=name,
            name=name,
            description=field_description,
            type="string",
            required=True,
        )
        for name in field_names
    ]

    tables = []
    for table_name in table_names:
        columns = [
            Column(
                column_id=name,
                name=name,
                description=column_description,
                type="string",
                required=True,
            )
            for name in column_names
        ]
        tables.append(
            Table(
                table_id=table_name,
                name=table_name,
                description=f"{table_name} table",
                columns=columns,
                required=False,
            )
        )

    now = datetime.now(timezone.utc)
    return ExtractionSchema(
        schema_id=schema_id,
        project_id="default",
        name=f"{schema_id} name",
        description="Test schema",
        version="v1",
        fields=fields,
        tables=tables,
        created_at=now,
        updated_at=now,
    )


def test_can_save_and_load_schema(tmp_path: Path) -> None:
    registry = SchemaRegistry(tmp_path)
    schema = _build_schema(schema_id="custom_v1")
    registry.save_schema(schema)
    loaded = registry.load_schema("custom_v1")
    assert loaded.schema_id == "custom_v1"
    assert len(loaded.fields) == 2
    assert len(loaded.tables) == 1


def test_can_list_schemas(tmp_path: Path) -> None:
    registry = SchemaRegistry(tmp_path)
    registry.save_schema(_build_schema(schema_id="a_v1"))
    registry.save_schema(_build_schema(schema_id="b_v1"))
    assert registry.list_schemas() == ["a_v1", "b_v1"]


def test_invoice_v1_loads_correctly() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    registry = SchemaRegistry(repo_root / "configs" / "schemas")
    schema = registry.load_schema("invoice_v1")
    assert schema.schema_id == "invoice_v1"
    assert [f.name for f in schema.fields] == [
        "invoice_id",
        "vendor_name",
        "invoice_date",
        "total_amount",
    ]
    assert [t.name for t in schema.tables] == ["line_items"]


def test_receipt_v1_loads_correctly() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    registry = SchemaRegistry(repo_root / "configs" / "schemas")
    schema = registry.load_schema("receipt_v1")
    assert schema.schema_id == "receipt_v1"
    assert [f.name for f in schema.fields] == [
        "merchant_name",
        "receipt_date",
        "total_amount",
    ]
    assert [t.name for t in schema.tables] == ["items"]


def test_duplicate_field_names_raise_value_error(tmp_path: Path) -> None:
    registry = SchemaRegistry(tmp_path)
    schema = _build_schema(field_names=["invoice_id", "invoice_id"])
    with pytest.raises(ValueError, match="Duplicate field name"):
        registry.save_schema(schema)


def test_duplicate_table_names_raise_value_error(tmp_path: Path) -> None:
    registry = SchemaRegistry(tmp_path)
    schema = _build_schema(table_names=["line_items", "line_items"])
    with pytest.raises(ValueError, match="Duplicate table name"):
        registry.save_schema(schema)


def test_duplicate_column_names_raise_value_error(tmp_path: Path) -> None:
    registry = SchemaRegistry(tmp_path)
    schema = _build_schema(column_names=["quantity", "quantity"])
    with pytest.raises(ValueError, match="Duplicate column name"):
        registry.save_schema(schema)


def test_missing_field_description_raises_value_error(tmp_path: Path) -> None:
    registry = SchemaRegistry(tmp_path)
    schema = _build_schema(field_description=None)
    with pytest.raises(ValueError, match="description is required"):
        registry.save_schema(schema)


def test_missing_column_description_raises_value_error(tmp_path: Path) -> None:
    registry = SchemaRegistry(tmp_path)
    schema = _build_schema(column_description=None)
    with pytest.raises(ValueError, match="description is required"):
        registry.save_schema(schema)

