from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from docai_core.contracts.domain import Column, ExtractionSchema, Field, Table
from docai_core.schemas.registry import SchemaRegistry

if TYPE_CHECKING:
    from docai_core.persistence.sqlite_store import ExtractionSchemaRecord

_DEFAULT_SCHEMA_DIR = Path(__file__).resolve().parents[2] / "configs" / "extraction_schemas"


def load_extraction_schema(
    schema_id: str,
    schema_dir: str | Path | None = None,
) -> ExtractionSchema:
    """Load an ExtractionSchema from the JSON config directory.

    Raises ValueError if schema_id is not found.
    """
    directory = Path(schema_dir) if schema_dir is not None else _DEFAULT_SCHEMA_DIR
    return SchemaRegistry(directory).load_schema(schema_id)


def load_schema_for_execution(schema_id: str, db_path: Path) -> ExtractionSchema:
    """Load ExtractionSchema for runtime use: built-in file first, then SQLite.

    Tries the file-backed config directory first so built-in schemas (invoice_basic,
    receipt_basic, etc.) continue to work without touching the database. Falls back
    to the persisted extraction_schemas table if the file is absent.

    Raises ValueError if schema_id is not found in either source.
    """
    try:
        return load_extraction_schema(schema_id)
    except ValueError:
        pass

    from docai_core.persistence.sqlite_store import SQLiteStore

    try:
        record = SQLiteStore(db_path).get_extraction_schema(schema_id)
    except ValueError:
        raise ValueError(f"Schema not found: {schema_id!r}")

    return _schema_from_record(record)


def _schema_from_record(record: "ExtractionSchemaRecord") -> ExtractionSchema:
    """Convert a persisted ExtractionSchemaRecord into an ExtractionSchema domain object."""
    import json as _json

    try:
        data: dict = _json.loads(record.schema_json)
    except Exception:
        data = {}

    fields = [
        Field(
            field_id=str(item.get("field_id") or item.get("id") or item.get("name", "")),
            name=str(item.get("name", "")),
            description=str(item.get("description") or "") or None,
            type=str(item.get("type") or "str"),
            required=bool(item.get("required", False)),
            examples=list(item.get("examples") or []),
            validation_rules=list(item.get("validation_rules") or []),
            aliases=list(item.get("aliases") or []),
        )
        for item in (data.get("fields") or [])
        if item.get("name")
    ]

    tables = [
        Table(
            table_id=str(t.get("table_id") or t.get("id") or t.get("name", "")),
            name=str(t.get("name", "")),
            description=str(t.get("description") or "") or None,
            columns=[
                Column(
                    column_id=str(c.get("column_id") or c.get("id") or c.get("name", "")),
                    name=str(c.get("name", "")),
                    description=str(c.get("description") or "") or None,
                    type=str(c.get("type") or "str"),
                    required=bool(c.get("required", False)),
                    examples=list(c.get("examples") or []),
                    validation_rules=list(c.get("validation_rules") or []),
                )
                for c in (t.get("columns") or [])
                if c.get("name")
            ],
            required=bool(t.get("required", False)),
            validation_rules=list(t.get("validation_rules") or []),
        )
        for t in (data.get("tables") or [])
        if t.get("name")
    ]

    return ExtractionSchema(
        schema_id=record.schema_id,
        project_id=record.project_id,
        name=record.name,
        description=None,
        version=str(record.version),
        fields=fields,
        tables=tables,
    )
