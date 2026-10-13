"""The optional PostgreSQL telemetry snapshot must publish as one unit."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Self

from idpo.pipeline.telemetry import persist_run_telemetry


class FakeCursor:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, query: str, values: object = None) -> None:
        if "INSERT INTO idpo_doc_telemetry" in query:
            self.connection.document_inserts += 1
            if self.connection.fail_on_document == self.connection.document_inserts:
                raise RuntimeError("simulated document insert failure")
        self.connection.pending.append((query, values))


class FakeConnection:
    def __init__(self, fail_on_document: int | None = None) -> None:
        self.fail_on_document = fail_on_document
        self.document_inserts = 0
        self.pending: list[tuple[str, object]] = []
        self.committed: list[tuple[str, object]] = []
        self.rolled_back = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, error_type: object, *_: object) -> None:
        if error_type is None:
            self.committed = self.pending.copy()
        else:
            self.rolled_back = True
        self.pending.clear()

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)


def _persist(monkeypatch, tmp_path, connection: FakeConnection) -> dict[str, object]:
    def connect(dsn: str, **options: object) -> FakeConnection:
        assert dsn == "postgresql://test"
        assert options.get("autocommit") is not True
        return connection

    monkeypatch.setenv("POSTGRES_URI", "postgresql://test")
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))
    return persist_run_telemetry(
        tmp_path,
        "run-1",
        [{"doc_id": "first"}, {"doc_id": "second"}],
        {"doc_count": 2, "processed_doc_count": 2, "failed_count": 0, "duration_ms": 10},
        [],
    )


def test_telemetry_commits_run_and_all_documents_together(monkeypatch, tmp_path):
    connection = FakeConnection()

    result = _persist(monkeypatch, tmp_path, connection)

    assert result == {"enabled": True, "status": "ok", "persisted_docs": 2}
    assert connection.document_inserts == 2
    queries = [query for query, _ in connection.committed]
    assert len(queries) == 6  # two tables, one run, one delete, two documents
    delete_index = next(index for index, query in enumerate(queries) if "DELETE FROM idpo_doc_telemetry" in query)
    first_document_index = next(index for index, query in enumerate(queries) if "INSERT INTO idpo_doc_telemetry" in query)
    assert delete_index < first_document_index
    assert not connection.rolled_back


def test_telemetry_rolls_back_header_and_earlier_documents_on_error(monkeypatch, tmp_path):
    connection = FakeConnection(fail_on_document=2)

    result = _persist(monkeypatch, tmp_path, connection)

    assert result["status"] == "error"
    assert result["warning"] == "telemetry_db_write_failed: RuntimeError"
    assert connection.document_inserts == 2
    assert connection.rolled_back
    assert connection.committed == []
