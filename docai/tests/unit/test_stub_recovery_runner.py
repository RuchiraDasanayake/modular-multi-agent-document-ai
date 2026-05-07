from datetime import datetime, timezone

from docai_core.contracts.domain import Document, DocumentProfile
from docai_core.recovery.stub_recovery_runner import StubRecoveryRunner


def test_stub_recovery_runner_builds_expected_report() -> None:
    now = datetime.now(timezone.utc)
    document = Document(
        document_id="doc-1",
        job_id="job-1",
        original_filename="invoice_001.pdf",
        file_path="invoice_001.pdf",
        status="uploaded",
        uploaded_at=now,
        profile=DocumentProfile(document_id="doc-1"),
    )

    report = StubRecoveryRunner().build_recovery_report(document)

    assert report.document_id == "doc-1"
    assert report.status == "not_attempted"
    assert report.attempted is False
    assert report.recovered_fields == []
    assert report.recovered_table_rows == []
    assert report.failed_items == []
    assert report.strategies_used == []
    assert report.summary is not None
    assert "stub" in report.summary
