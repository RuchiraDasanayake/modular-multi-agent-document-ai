from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from docai_core.contracts.domain import Column, ExtractionSchema, Field, Table


class SchemaRegistry:
    def __init__(self, schema_dir: str | Path) -> None:
        self.schema_dir = Path(schema_dir)
        self.schema_dir.mkdir(parents=True, exist_ok=True)

    def list_schemas(self) -> list[str]:
        return sorted(path.stem for path in self.schema_dir.glob("*.json"))

    def schema_path(self, schema_id: str) -> Path:
        return self.schema_dir / f"{schema_id}.json"

    def load_schema(self, schema_id: str) -> ExtractionSchema:
        path = self.schema_path(schema_id)
        if not path.exists():
            raise ValueError(f"Schema not found: {schema_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        self._validate_schema_dict(data)
        return self._build_schema(data)

    def save_schema(self, schema: ExtractionSchema) -> Path:
        data = schema.to_dict()
        self._validate_schema_dict(data)
        path = self.schema_path(data["schema_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._json_safe(data), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def _validate_schema_dict(self, data: dict[str, Any]) -> None:
        schema_id = data.get("schema_id")
        name = data.get("name")
        version = data.get("version")
        fields = data.get("fields")
        tables = data.get("tables")

        if not schema_id:
            raise ValueError("Invalid schema: schema_id is required")
        if not name:
            raise ValueError("Invalid schema: name is required")
        if not version:
            raise ValueError("Invalid schema: version is required")
        if not isinstance(fields, list):
            raise ValueError("Invalid schema: fields must be a list")
        if not isinstance(tables, list):
            raise ValueError("Invalid schema: tables must be a list")

        field_names: set[str] = set()
        for idx, item in enumerate(fields):
            field_name = item.get("name")
            field_description = item.get("description")
            if not field_name:
                raise ValueError(f"Invalid field at index {idx}: name is required")
            if not field_description:
                raise ValueError(f"Invalid field '{field_name}': description is required")
            if field_name in field_names:
                raise ValueError(f"Duplicate field name: {field_name}")
            field_names.add(field_name)

        table_names: set[str] = set()
        for table_idx, table in enumerate(tables):
            table_name = table.get("name")
            columns = table.get("columns")
            if not table_name:
                raise ValueError(f"Invalid table at index {table_idx}: name is required")
            if table_name in table_names:
                raise ValueError(f"Duplicate table name: {table_name}")
            table_names.add(table_name)

            if not isinstance(columns, list):
                raise ValueError(f"Invalid table '{table_name}': columns must be a list")

            column_names: set[str] = set()
            for col_idx, column in enumerate(columns):
                column_name = column.get("name")
                column_description = column.get("description")
                if not column_name:
                    raise ValueError(
                        f"Invalid column at index {col_idx} in table '{table_name}': name is required"
                    )
                if not column_description:
                    raise ValueError(
                        f"Invalid column '{column_name}' in table '{table_name}': description is required"
                    )
                if column_name in column_names:
                    raise ValueError(f"Duplicate column name in table '{table_name}': {column_name}")
                column_names.add(column_name)

    def _build_schema(self, data: dict[str, Any]) -> ExtractionSchema:
        fields: list[Field] = []
        for item in data["fields"]:
            fields.append(
                Field(
                    field_id=item.get("field_id", item["name"]),
                    name=item["name"],
                    description=item.get("description"),
                    type=item.get("type", "string"),
                    required=bool(item.get("required", False)),
                    examples=list(item.get("examples", [])),
                    validation_rules=list(item.get("validation_rules", [])),
                    aliases=list(item.get("aliases", [])),
                )
            )

        tables: list[Table] = []
        for table in data["tables"]:
            columns: list[Column] = []
            for column in table.get("columns", []):
                columns.append(
                    Column(
                        column_id=column.get("column_id", column["name"]),
                        name=column["name"],
                        description=column.get("description"),
                        type=column.get("type", "string"),
                        required=bool(column.get("required", False)),
                        examples=list(column.get("examples", [])),
                        validation_rules=list(column.get("validation_rules", [])),
                    )
                )
            tables.append(
                Table(
                    table_id=table.get("table_id", table["name"]),
                    name=table["name"],
                    description=table.get("description"),
                    columns=columns,
                    required=bool(table.get("required", False)),
                    validation_rules=list(table.get("validation_rules", [])),
                )
            )

        created_at = self._parse_datetime(data.get("created_at"))
        updated_at = self._parse_datetime(data.get("updated_at"))

        return ExtractionSchema(
            schema_id=data["schema_id"],
            project_id=data.get("project_id", "default"),
            name=data["name"],
            description=data.get("description"),
            version=data["version"],
            fields=fields,
            tables=tables,
            created_at=created_at,
            updated_at=updated_at,
        )

    def _parse_datetime(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        raise ValueError(f"Invalid datetime value: {value!r}")

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {k: self._json_safe(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._json_safe(v) for v in value]
        return value

