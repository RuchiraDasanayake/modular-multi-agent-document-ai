from __future__ import annotations

from dataclasses import dataclass

from docai_core.contracts.domain import Document, RecoveryReport


@dataclass(slots=True)
class StubRecoveryRunner:
    """Stub recovery runner for runtime spine validation only. Do not add real recovery logic here."""

    def build_recovery_report(self, document: Document) -> RecoveryReport:
        return RecoveryReport(
            document_id=document.document_id,
            status="not_attempted",
            attempted=False,
            recovered_fields=[],
            recovered_table_rows=[],
            failed_items=[],
            strategies_used=[],
            summary="stub recovery not attempted",
        )
